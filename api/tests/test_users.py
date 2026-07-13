from datetime import datetime, timezone

from django.urls import reverse

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from api.tests.common import make_desktop
from researcher_workspace.tests.factories import FeatureFactory, UserFactory
from vm_manager.constants import NO_VM, VM_OKAY, VM_SHELVED

utc = timezone.utc


class UserAPITestBase(APITestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()
        self.staff_user = UserFactory.create(is_staff=True)
        self.staff_token = Token.objects.create(user=self.staff_user)

    def authenticate(self, keyword='Token'):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'{keyword} {self.staff_token.key}')


class UserListTests(UserAPITestBase):

    def test_anonymous_user_denied(self):
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_non_staff_user_denied(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)

    def test_staff_token_allowed(self):
        self.authenticate()
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)

    def test_bearer_keyword_not_accepted(self):
        self.authenticate(keyword='Bearer')
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_staff_session_allowed(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)

    def test_pagination_envelope(self):
        self.authenticate()
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        for key in ('count', 'next', 'previous', 'results'):
            self.assertIn(key, response.data)
        self.assertEqual(2, response.data['count'])

    def test_pagination_page_size(self):
        self.authenticate()
        response = self.client.get(reverse('api:user-list'),
                                   {'page_size': 1})
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(2, response.data['count'])
        self.assertEqual(1, len(response.data['results']))
        self.assertIsNotNone(response.data['next'])

    def test_filter_is_staff(self):
        self.authenticate()
        response = self.client.get(reverse('api:user-list'),
                                   {'is_staff': 'true'})
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        self.assertEqual(self.staff_user.username,
                         response.data['results'][0]['username'])

    def test_filter_last_login_gte(self):
        cutoff = datetime(2026, 1, 1, tzinfo=utc)
        UserFactory.create(last_login=datetime(2025, 6, 1, tzinfo=utc))
        recent = UserFactory.create(
            last_login=datetime(2026, 3, 1, tzinfo=utc))
        self.authenticate()
        response = self.client.get(
            reverse('api:user-list'),
            {'last_login__gte': cutoff.isoformat(),
             'ordering': '-last_login'})
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        self.assertEqual(recent.username,
                         response.data['results'][0]['username'])

    def test_search(self):
        target = UserFactory.create(email='jane.doe@example.edu.au',
                                    username='jane.doe@example.edu.au')
        self.authenticate()
        response = self.client.get(reverse('api:user-list'),
                                   {'search': 'jane.doe'})
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        self.assertEqual(target.username,
                         response.data['results'][0]['username'])

    def test_list_fields(self):
        self.authenticate()
        response = self.client.get(reverse('api:user-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        result = response.data['results'][0]
        expected = {'username', 'email', 'first_name', 'last_name',
                    'sub', 'is_staff', 'is_superuser', 'is_active',
                    'date_joined', 'last_login', 'terms_version',
                    'date_agreed_terms', 'groups'}
        self.assertEqual(expected, set(result.keys()))


class UserDetailTests(UserAPITestBase):

    def detail_url(self, username):
        return reverse('api:user-detail', kwargs={'username': username})

    def test_anonymous_user_denied(self):
        response = self.client.get(self.detail_url(self.user.username))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_lookup_by_email_username(self):
        # Usernames are email addresses, so the lookup must cope with
        # dots and '@' in the URL.
        target = UserFactory.create(email='jane.doe@example.edu.au',
                                    username='jane.doe@example.edu.au')
        self.authenticate()
        response = self.client.get(self.detail_url(target.username))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(target.username, response.data['username'])
        self.assertEqual(target.sub, response.data['sub'])
        self.assertIn('desktops', response.data)
        self.assertIn('groups', response.data)

    def test_unknown_username(self):
        self.authenticate()
        response = self.client.get(
            self.detail_url('nosuchuser@example.edu.au'))
        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)

    def test_desktops_summary(self):
        feature = FeatureFactory.create(app_name='feature')
        vm_status = make_desktop(self.user, 'ubuntu', feature,
                                 status=VM_SHELVED)
        self.authenticate()
        response = self.client.get(self.detail_url(self.user.username))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, len(response.data['desktops']))
        desktop = response.data['desktops'][0]
        self.assertEqual('ubuntu', desktop['desktop_type'])
        self.assertEqual(VM_SHELVED, desktop['status'])
        self.assertEqual(str(vm_status.instance.id),
                         desktop['instance_id'])

    def test_desktops_only_latest_per_type(self):
        feature = FeatureFactory.create(app_name='feature')
        make_desktop(self.user, 'ubuntu', feature, status=VM_OKAY)
        latest = make_desktop(self.user, 'ubuntu', feature,
                              status=VM_SHELVED)
        self.authenticate()
        response = self.client.get(self.detail_url(self.user.username))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, len(response.data['desktops']))
        self.assertEqual(str(latest.instance.id),
                         response.data['desktops'][0]['instance_id'])

    def test_desktops_excludes_deleted(self):
        feature = FeatureFactory.create(app_name='feature')
        make_desktop(self.user, 'ubuntu', feature, status=NO_VM,
                     deleted=datetime.now(utc))
        self.authenticate()
        response = self.client.get(self.detail_url(self.user.username))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual([], response.data['desktops'])

    def test_desktops_includes_shelved(self):
        # Shelving deletes the instance but the desktop still exists;
        # the status field is the source of truth.
        feature = FeatureFactory.create(app_name='feature')
        make_desktop(self.user, 'ubuntu', feature, status=VM_SHELVED,
                     deleted=datetime.now(utc))
        self.authenticate()
        response = self.client.get(self.detail_url(self.user.username))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, len(response.data['desktops']))
        self.assertEqual(VM_SHELVED,
                         response.data['desktops'][0]['status'])

    def test_no_desktops(self):
        self.authenticate()
        response = self.client.get(self.detail_url(self.user.username))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual([], response.data['desktops'])
