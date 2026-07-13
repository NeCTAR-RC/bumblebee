from datetime import datetime, timezone

from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from api.models import ServiceToken
from api.tests.common import make_desktop
from researcher_workspace.tests.factories import FeatureFactory, UserFactory
from vm_manager.constants import NO_VM, VM_OKAY, VM_SHELVED

utc = timezone.utc


class DesktopAPITests(APITestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()
        self.other_user = UserFactory.create()
        self.feature = FeatureFactory.create(app_name='feature')
        self.token, self.key = ServiceToken.generate('test-cron')

    def authenticate(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.key}')

    def test_anonymous_user_denied(self):
        response = self.client.get(reverse('api:desktop-list'))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_list_fields(self):
        vm_status = make_desktop(self.user, 'ubuntu', self.feature)
        self.authenticate()
        response = self.client.get(reverse('api:desktop-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        desktop = response.data['results'][0]
        expected = {'id', 'user', 'desktop_type', 'status', 'zone',
                    'instance_id', 'created'}
        self.assertEqual(expected, set(desktop.keys()))
        self.assertEqual(self.user.username, desktop['user'])
        self.assertEqual('ubuntu', desktop['desktop_type'])
        self.assertEqual(VM_OKAY, desktop['status'])
        self.assertEqual('QRIScloud', desktop['zone'])
        self.assertEqual(str(vm_status.instance.id),
                         desktop['instance_id'])

    def test_only_latest_per_user_and_type(self):
        make_desktop(self.user, 'ubuntu', self.feature, status=VM_OKAY)
        latest = make_desktop(self.user, 'ubuntu', self.feature,
                              status=VM_SHELVED)
        self.authenticate()
        response = self.client.get(reverse('api:desktop-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        self.assertEqual(latest.id, response.data['results'][0]['id'])
        self.assertEqual(VM_SHELVED,
                         response.data['results'][0]['status'])

    def test_excludes_deleted_desktops(self):
        make_desktop(self.user, 'ubuntu', self.feature, status=NO_VM,
                     deleted=datetime.now(utc))
        self.authenticate()
        response = self.client.get(reverse('api:desktop-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(0, response.data['count'])

    def test_includes_shelved_with_deleted_instance(self):
        # Shelving deletes the instance but the desktop still exists
        make_desktop(self.user, 'ubuntu', self.feature,
                     status=VM_SHELVED, deleted=datetime.now(utc))
        self.authenticate()
        response = self.client.get(reverse('api:desktop-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])

    def test_filter_desktop_type_and_status(self):
        # e.g. which users have a neurodesktop shelved?
        make_desktop(self.user, 'neurodesktop', self.feature,
                     status=VM_SHELVED, deleted=datetime.now(utc))
        make_desktop(self.other_user, 'neurodesktop', self.feature,
                     status=VM_OKAY)
        make_desktop(self.user, 'ubuntu', self.feature,
                     status=VM_SHELVED, deleted=datetime.now(utc))
        self.authenticate()
        response = self.client.get(
            reverse('api:desktop-list'),
            {'desktop_type': 'neurodesktop', 'status': VM_SHELVED})
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        desktop = response.data['results'][0]
        self.assertEqual(self.user.username, desktop['user'])
        self.assertEqual('neurodesktop', desktop['desktop_type'])

    def test_filter_by_user(self):
        make_desktop(self.user, 'ubuntu', self.feature)
        make_desktop(self.other_user, 'ubuntu', self.feature)
        self.authenticate()
        response = self.client.get(
            reverse('api:desktop-list'),
            {'user': self.other_user.username})
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        self.assertEqual(self.other_user.username,
                         response.data['results'][0]['user'])

    def test_detail(self):
        vm_status = make_desktop(self.user, 'ubuntu', self.feature)
        self.authenticate()
        response = self.client.get(
            reverse('api:desktop-detail', kwargs={'pk': vm_status.pk}))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(self.user.username, response.data['user'])
