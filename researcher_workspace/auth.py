import logging
import unicodedata

from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from guacamole import models as guac_models


logger = logging.getLogger(__name__)

# Roles to determine user level
ADMIN_ROLES = ['admin']
STAFF_ROLES = ADMIN_ROLES + ['staff']


def get_or_create_guac_objects(user):
    """Create or update user's Guacamole objects.

    This create the Guacamole entity and user objects for the provided
    Django user object.  If the associated email address changes, we will end
    up creating new Guacamole objects.
    """

    gentity, created = guac_models.GuacamoleEntity.objects.get_or_create(
        name=user.email, type='USER',)

    guser = None
    if not created:
        try:
            guser = guac_models.GuacamoleUser.objects.get(
                email_address=user.email)
        except guac_models.GuacamoleUser.DoesNotExist:
            pass

    if not guser:
        guser = guac_models.GuacamoleUser.objects.create(
            entity=gentity,
            email_address=user.email,
            full_name=user.get_full_name(),
            password_hash='x',
            disabled=False,
            expired=False)
    else:
        guser.email_address = user.email
        guser.full_name = user.get_full_name()
        guser.password_hash = 'x'
        guser.disabled = False
        guser.expired = False
        guser.save()

    return (gentity, guser)


class ClassicAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username=username,
                                    password=password, **kwargs)
        if user:
            get_or_create_guac_objects(user)
        return user


class OIDCAuthBackend(OIDCAuthenticationBackend):

    def create_user(self, claims):
        email = claims.get('email')
        username = self.get_username(claims)
        sub = claims.get('sub')  # OIDC persistent ID
        first_name = claims.get('given_name')
        last_name = claims.get('family_name')

        existing = self.UserModel.objects.filter(email__iexact=email).first()
        if existing:
            # username/sub mismatch
            logger.error(
                f"Login failed for {username}: "
                f"Sub value {sub} did not match existing value {existing.sub}")
            return

        user = self.UserModel.objects.create_user(
            username, email=email, sub=sub,
            first_name=first_name, last_name=last_name)

        # Assign Django staff/admin settings per the claims from OIDC
        groups = claims.get(settings.OIDC_CLAIM_GROUPS_KEY, [])
        user.is_staff = any(i in STAFF_ROLES for i in groups)
        user.is_superuser = any(i in ADMIN_ROLES for i in groups)
        user.save()

        # Create Guacamole user objects
        get_or_create_guac_objects(user)

        return user

    def update_user(self, user, claims):
        # Fetch Guac objects based on the previous user details.
        gentity, guser = get_or_create_guac_objects(user)

        # Update Django user values per claims from OIDC
        user.first_name = claims.get('given_name')
        user.last_name = claims.get('family_name')
        user.email = claims.get('email')
        user.sub = claims.get('sub')
        user.username = generate_username(user.email)

        # Update Django staff/admin settings per claims from OIDC
        groups = claims.get(settings.OIDC_CLAIM_GROUPS_KEY, [])
        user.is_staff = any(i in STAFF_ROLES for i in groups)
        user.is_superuser = any(i in ADMIN_ROLES for i in groups)
        user.save()

        # Update Guac objects with updated details from OIDC
        gentity.name = user.email
        gentity.save()

        guser.email_address = user.email
        guser.full_name = user.get_full_name()
        guser.password_hash = 'x'
        guser.disabled = False
        guser.expired = False
        guser.save()

        return user

    def filter_users_by_claims(self, claims):
        "Return all users matching the specified sub."

        email = claims.get('email')
        sub = claims.get('sub')
        if not sub or not email:
            return self.UserModel.objects.none()

        users = self.UserModel.objects.filter(sub=sub)
        if not users:
            users = self.UserModel.objects.filter(
                email__iexact=email).filter(sub__isnull=True)
        return users

    def verify_claims(self, claims):
        verified = super().verify_claims(claims)

        if settings.OIDC_ALLOW_GROUPS and settings.OIDC_CLAIM_GROUPS_KEY:
            groups = claims.get(settings.OIDC_CLAIM_GROUPS_KEY, [])
            matches = set(settings.OIDC_ALLOW_GROUPS) & set(groups)
            email = claims.get('email')
            if matches:
                logger.info(f"Login for {email} granted with matched groups: "
                            f"{matches}.")
            else:
                logger.warning(
                    f"Login for {email} is denied due to missing OIDC roles. "
                    f"Require {settings.OIDC_ALLOW_GROUPS}, found {groups}")
                return

        return verified


def generate_username(email):
    # Enabled with settings.OIDC_USERNAME_ALGO in settings.py
    # Using Python 3 and Django 1.11+, usernames can contain alphanumeric
    # (ascii and unicode), _, @, +, . and - characters. So we normalize
    # it and slice at 150 characters.
    # https://mozilla-django-oidc.readthedocs.io/en/stable/installation.html#generating-usernames
    return unicodedata.normalize('NFKC', email)[:150]
