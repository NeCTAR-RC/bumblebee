from io import StringIO

from django.core.management import call_command, CommandError
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from api.models import ServiceToken


class ServiceTokenTests(APITestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.token, self.key = ServiceToken.generate('test-cron')

    def authenticate(self, key=None, keyword='Token'):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'{keyword} {key or self.key}')

    def test_key_is_hashed(self):
        self.assertTrue(self.key.startswith(ServiceToken.KEY_PREFIX))
        self.assertNotEqual(self.key, self.token.hashed_key)
        self.assertEqual(ServiceToken.hash_key(self.key),
                         self.token.hashed_key)
        self.assertEqual(self.key[:12], self.token.prefix)

    def test_service_token_allowed(self):
        self.authenticate()
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)

    def test_service_token_bearer_keyword_not_accepted(self):
        self.authenticate(keyword='Bearer')
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_invalid_service_token_denied(self):
        self.authenticate(key=f'{ServiceToken.KEY_PREFIX}bogus')
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_deactivated_service_token_denied(self):
        self.token.active = False
        self.token.save()
        self.authenticate()
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_last_used_updated(self):
        self.assertIsNone(self.token.last_used)
        self.authenticate()
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.last_used)

    def test_service_token_write_denied(self):
        # Service tokens are read-only principals: unsafe methods are
        # rejected by permission (403), not just by the read-only
        # viewsets (405).
        self.authenticate()
        for url in ('api:user-list', 'api:desktop-list',
                    'api:volume-list', 'api:instance-list',
                    'api:vmstatus-list', 'api:resize-list'):
            response = self.client.post(reverse(url), {})
            self.assertEqual(status.HTTP_403_FORBIDDEN,
                             response.status_code, url)

    def test_non_service_key_falls_through(self):
        # A non 'svc-' key must not be claimed by service token auth;
        # it falls through to user token auth and fails there.
        self.authenticate(key='not-a-service-key')
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_create_service_token_command(self):
        out = StringIO()
        call_command('create_service_token', 'reporting-cron',
                     stdout=out)
        output = out.getvalue()
        self.assertIn('reporting-cron', output)
        token = ServiceToken.objects.get(name='reporting-cron')
        self.assertIn(token.prefix, output)

    def test_create_service_token_command_duplicate(self):
        with self.assertRaises(CommandError):
            call_command('create_service_token', 'test-cron')
