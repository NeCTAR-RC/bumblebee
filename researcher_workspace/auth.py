import logging
import unicodedata

from django.conf import settings
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from guacamole import models as guac_models


logger = logging.getLogger(__name__)

# Roles to determine user level
ADMIN_ROLES = ['admin', 'coreservices']
STAFF_ROLES = ADMIN_ROLES + ['staff']


class NectarAuthBackend(OIDCAuthenticationBackend):

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

        # Automatically assign staff/admin from Keycloak
        roles = claims.get('roles', [])
        user.is_staff = any(i in STAFF_ROLES for i in roles)
        user.is_superuser = any(i in ADMIN_ROLES for i in roles)

        # Create Guacamole user objects
        gentity = guac_models.GuacamoleEntity.objects.create(
            name=user.email, type='USER',)

        guser = guac_models.GuacamoleUser.objects.create(
            entity=gentity,
            email_address=user.email,
            full_name=user.get_full_name(),
            password_hash='x',
            disabled=False,
            expired=False,)

        user.save()
        return user

    def update_user(self, user, claims):
        # Before attempting to update user fields, get guac user object
        # based on the pre-updated values from our db
        try:
            gentity = guac_models.GuacamoleEntity.objects.get(
                name=user.email)
        except guac_models.GuacamoleEntity.DoesNotExist:
            gentity = None

        try:
            guser = guac_models.GuacamoleUser.objects.get(
                email_address=user.email)
        except guac_models.GuacamoleUser.DoesNotExist:
            guser = None

        # Update user values
        user.first_name = claims.get('given_name')
        user.last_name = claims.get('family_name')
        user.email = claims.get('email')
        user.sub = claims.get('sub')
        user.username = generate_username(user.email)

        # Automatically assign staff/admin from Keycloak
        roles = claims.get('roles', [])
        user.is_staff = any(i in STAFF_ROLES for i in roles)
        user.is_superuser = any(i in ADMIN_ROLES for i in roles)

        if gentity:
            gentity.name = user.email
            gentity.save()
        else:
            gentity = guac_models.GuacamoleEntity.objects.create(
                name=user.email,
                type='USER',)

        if guser:
            guser.email_address = user.email
            guser.full_name = user.get_full_name()
            guser.password_hash = 'x'
            guser.disabled = False
            guser.expired = False
            guser.save()
        else:
            guser = guac_models.GuacamoleUser.objects.create(
                entity=gentity,
                email_address=user.email,
                full_name=user.get_full_name(),
                password_hash='x',
                disabled=False,
                expired=False,)

        user.save()
        return user

    def filter_users_by_claims(self, claims):
        """Return all users matching the specified sub."""
        email = claims.get('email')
        sub = claims.get('sub')
        if not sub or not email:
            return self.UserModel.objects.none()

        users = self.UserModel.objects.filter(sub__iexact=sub)
        if not users:
            users = self.UserModel.objects.filter(
                email__iexact=email).filter(sub__isnull=True)
        return users

    def verify_claims(self, claims):
        verified = super(NectarAuthBackend, self).verify_claims(claims)

        # Currently we only allow Australian users via AAF
        federation = claims.get('federation', 'not found')

        if federation != 'aaf' and settings.REQUIRE_AAF:
            email = claims.get('email')
            logger.warning(
                f"Login for {email} is denied due to federation ({federation}) "
                f"not being set to aaf")
            return

        return verified


def generate_username(email):
    # Enabled with settings.OIDC_USERNAME_ALGO in settings.py
    # Using Python 3 and Django 1.11+, usernames can contain alphanumeric
    # (ascii and unicode), _, @, +, . and - characters. So we normalize
    # it and slice at 150 characters.
    # https://mozilla-django-oidc.readthedocs.io/en/stable/installation.html#generating-usernames
    return unicodedata.normalize('NFKC', email)[:150]
