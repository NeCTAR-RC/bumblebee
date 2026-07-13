from django.utils import timezone

from rest_framework import authentication
from rest_framework import exceptions

from api.models import ServiceToken


class ServiceAccount:
    """A synthetic principal representing an authenticated service.

    Not backed by a User row.  Presents the minimal user-like
    interface that DRF and its IsAdminUser permission expect.
    """

    is_staff = True
    is_superuser = False
    is_active = True
    is_authenticated = True
    is_anonymous = False

    def __init__(self, token):
        self.token = token
        self.username = f'service:{token.name}'

    def __str__(self):
        return self.username


class ServiceTokenAuthentication(authentication.BaseAuthentication):
    """Authenticate service tokens that are not tied to a user account.

    Only handles keys carrying the ServiceToken prefix; anything else
    is passed through to the next authentication class, so user
    tokens keep working with the same 'Token' keyword.  Must be
    listed before the user token class in
    DEFAULT_AUTHENTICATION_CLASSES.
    """

    keyword = 'Token'

    def authenticate(self, request):
        auth = authentication.get_authorization_header(request).split()
        if len(auth) != 2:
            return None
        try:
            keyword = auth[0].decode()
            key = auth[1].decode()
        except UnicodeError:
            return None
        if keyword != self.keyword:
            return None
        if not key.startswith(ServiceToken.KEY_PREFIX):
            # Not a service token: let other authenticators handle it
            return None
        try:
            token = ServiceToken.objects.get(
                hashed_key=ServiceToken.hash_key(key))
        except ServiceToken.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid service token.')
        if not token.active:
            raise exceptions.AuthenticationFailed(
                'Service token has been deactivated.')
        ServiceToken.objects.filter(pk=token.pk).update(
            last_used=timezone.now())
        return (ServiceAccount(token), token)

    def authenticate_header(self, request):
        return self.keyword
