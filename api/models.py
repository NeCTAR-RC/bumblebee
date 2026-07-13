import hashlib
import secrets

from django.db import models


class ServiceToken(models.Model):
    """An API token for a service, not tied to a user account.

    Intended for cron jobs and other machine consumers where a real
    user account (normally provisioned via OIDC) is not appropriate.

    The token key is stored as a SHA-256 hash and is only shown once,
    at creation time.  Keys carry a 'svc-' prefix so that the
    authentication layer can distinguish them from user tokens.
    """

    KEY_PREFIX = 'svc-'

    name = models.CharField(max_length=64, unique=True)
    hashed_key = models.CharField(max_length=64, unique=True)
    # The first few characters of the key, for identification only
    prefix = models.CharField(max_length=12)
    created = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    @staticmethod
    def hash_key(key):
        return hashlib.sha256(key.encode()).hexdigest()

    @classmethod
    def generate(cls, name):
        """Create a token and return (token, key).

        The plaintext key is not stored; this is the only time it is
        available.
        """
        key = cls.KEY_PREFIX + secrets.token_hex(20)
        token = cls.objects.create(
            name=name, hashed_key=cls.hash_key(key), prefix=key[:12])
        return token, key

    def __str__(self):
        return self.name
