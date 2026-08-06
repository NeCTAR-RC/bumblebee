from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from api.models import ServiceToken
from api.tests.common import make_desktop
from researcher_workspace.tests.factories import FeatureFactory, UserFactory
from vm_manager.tests.factories import ResizeFactory


class ResourceAPITestCase(APITestCase):
    """Common fixtures for the model resource endpoints."""

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()
        self.other_user = UserFactory.create()
        self.feature = FeatureFactory.create(app_name='feature')
        self.token, self.key = ServiceToken.generate('test-cron')

    def authenticate(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.key}')

    def make_error_desktop(self, user, desktop_id, message='boom'):
        """Make a desktop with error flags set.

        The VMStatus error propagates to the instance and volume,
        as in production error records.
        """
        vm_status = make_desktop(user, desktop_id, self.feature)
        vm_status.error(message)
        return vm_status


class VolumeAPITests(ResourceAPITestCase):

    def test_anonymous_user_denied(self):
        response = self.client.get(reverse('api:volume-list'))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_list_fields(self):
        vm_status = make_desktop(self.user, 'ubuntu', self.feature)
        volume = vm_status.instance.boot_volume
        self.authenticate()
        response = self.client.get(reverse('api:volume-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        result = response.data['results'][0]
        expected = {'id', 'user', 'desktop_type', 'zone', 'image',
                    'flavor', 'hostname_id', 'created', 'ready',
                    'checked_in', 'shelved_at', 'archived_at',
                    'rebooted_at', 'backup_id', 'expires',
                    'backup_expires', 'marked_for_deletion', 'deleted',
                    'error_flag', 'error_message'}
        self.assertEqual(expected, set(result.keys()))
        self.assertEqual(str(volume.id), str(result['id']))
        self.assertEqual(self.user.username, result['user'])
        self.assertEqual('ubuntu', result['desktop_type'])
        self.assertEqual('QRIScloud', result['zone'])

    def test_filter_error(self):
        make_desktop(self.user, 'ubuntu', self.feature)
        errored = self.make_error_desktop(self.other_user, 'centos')
        self.authenticate()
        response = self.client.get(reverse('api:volume-list'),
                                   {'error': 'true'})
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        result = response.data['results'][0]
        self.assertEqual(str(errored.instance.boot_volume.id),
                         str(result['id']))
        self.assertEqual('boom', result['error_message'])
        response = self.client.get(reverse('api:volume-list'),
                                   {'error': 'false'})
        self.assertEqual(1, response.data['count'])
        self.assertEqual(self.user.username,
                         response.data['results'][0]['user'])

    def test_detail(self):
        vm_status = make_desktop(self.user, 'ubuntu', self.feature)
        volume = vm_status.instance.boot_volume
        self.authenticate()
        response = self.client.get(
            reverse('api:volume-detail', kwargs={'pk': volume.pk}))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(self.user.username, response.data['user'])


class InstanceAPITests(ResourceAPITestCase):

    def test_anonymous_user_denied(self):
        response = self.client.get(reverse('api:instance-list'))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_list_fields_no_credentials(self):
        vm_status = make_desktop(self.user, 'ubuntu', self.feature)
        instance = vm_status.instance
        self.authenticate()
        response = self.client.get(reverse('api:instance-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        result = response.data['results'][0]
        expected = {'id', 'user', 'boot_volume_id', 'ip_address',
                    'created', 'expires', 'marked_for_deletion',
                    'deleted', 'error_flag', 'error_message'}
        self.assertEqual(expected, set(result.keys()))
        # The VM's local login credentials must never appear
        self.assertNotIn('username', result)
        self.assertNotIn('password', result)
        self.assertEqual(str(instance.id), str(result['id']))
        self.assertEqual(str(instance.boot_volume.id),
                         result['boot_volume_id'])

    def test_filter_by_volume(self):
        vm_status = make_desktop(self.user, 'ubuntu', self.feature)
        make_desktop(self.other_user, 'ubuntu', self.feature)
        instance = vm_status.instance
        self.authenticate()
        response = self.client.get(
            reverse('api:instance-list'),
            {'volume': str(instance.boot_volume.id)})
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        self.assertEqual(str(instance.id),
                         str(response.data['results'][0]['id']))

    def test_filter_error(self):
        make_desktop(self.user, 'ubuntu', self.feature)
        errored = self.make_error_desktop(self.other_user, 'centos')
        self.authenticate()
        response = self.client.get(reverse('api:instance-list'),
                                   {'error': 'true'})
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        self.assertEqual(str(errored.instance.id),
                         str(response.data['results'][0]['id']))


class VMStatusAPITests(ResourceAPITestCase):

    def test_anonymous_user_denied(self):
        response = self.client.get(reverse('api:vmstatus-list'))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_full_history(self):
        # Two generations of the same desktop: /desktops/ reports only
        # the latest, /vmstatuses/ reports both.
        make_desktop(self.user, 'ubuntu', self.feature)
        make_desktop(self.user, 'ubuntu', self.feature)
        self.authenticate()
        response = self.client.get(reverse('api:vmstatus-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(2, response.data['count'])
        response = self.client.get(reverse('api:desktop-list'))
        self.assertEqual(1, response.data['count'])

    def test_list_fields(self):
        vm_status = make_desktop(self.user, 'ubuntu', self.feature)
        self.authenticate()
        response = self.client.get(reverse('api:vmstatus-list'))
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        result = response.data['results'][0]
        expected = {'id', 'user', 'desktop_type', 'status',
                    'status_progress', 'status_message', 'instance_id',
                    'created', 'wait_time'}
        self.assertEqual(expected, set(result.keys()))
        self.assertEqual(str(vm_status.instance.id),
                         result['instance_id'])

    def test_filter_by_instance(self):
        vm_status = make_desktop(self.user, 'ubuntu', self.feature)
        make_desktop(self.other_user, 'ubuntu', self.feature)
        self.authenticate()
        response = self.client.get(
            reverse('api:vmstatus-list'),
            {'instance': str(vm_status.instance.id)})
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        self.assertEqual(vm_status.id,
                         response.data['results'][0]['id'])


class ResizeAPITests(ResourceAPITestCase):

    def test_anonymous_user_denied(self):
        response = self.client.get(reverse('api:resize-list'))
        self.assertEqual(status.HTTP_401_UNAUTHORIZED,
                         response.status_code)

    def test_filter_unreverted(self):
        vm_status = make_desktop(self.user, 'ubuntu', self.feature)
        resize = ResizeFactory.create(instance=vm_status.instance)
        self.authenticate()
        response = self.client.get(reverse('api:resize-list'),
                                   {'reverted': 'false'})
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(1, response.data['count'])
        result = response.data['results'][0]
        expected = {'id', 'instance_id', 'requested', 'reverted',
                    'expires'}
        self.assertEqual(expected, set(result.keys()))
        self.assertEqual(resize.id, result['id'])
        self.assertEqual(str(vm_status.instance.id),
                         result['instance_id'])
        response = self.client.get(reverse('api:resize-list'),
                                   {'reverted': 'true'})
        self.assertEqual(0, response.data['count'])
