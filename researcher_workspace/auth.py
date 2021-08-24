from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from guacamole import models as guac_models

class NectarAuthBackend(OIDCAuthenticationBackend):
    def create_user(self, claims):
        print('creating user')
        user = super(NectarAuthBackend, self).create_user(claims)
        user.first_name = claims.get('given_name', '')
        user.last_name = claims.get('family_name', '')

        guac_entity = guac_models.GuacamoleEntity()
        guac_entity.name = user.email
        guac_entity.type = 'USER'

        guac_user = guac_models.GuacamoleUser()
        guac_user.entity = guac_entity
        guac_user.email_address = user.email
        guac_user.full_name = user.get_full_name()
        guac_user.password_hash = 'x'
        guac_user.disabled = False
        guac_user.expired = False

        guac_entity.save()
        guac_user.save()
        user.save()
        return user

    def update_user(self, user, claims):
        user.first_name = claims.get('given_name', '')
        user.last_name = claims.get('family_name', '')
        user.save()
        return user


def generate_username(email):
    return email

