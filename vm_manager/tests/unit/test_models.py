import pdb

import uuid
import copy
from datetime import datetime, timedelta, timezone

from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase

from researcher_workspace.settings import GUACAMOLE_URL
from researcher_workspace.tests.factories import FeatureFactory, UserFactory
from researcher_desktop.tests.factories import DesktopTypeFactory
from guacamole.models import GuacamoleEntity, GuacamoleConnectionParameter, \
    GuacamoleConnectionPermission
from guacamole.tests.factories import GuacamoleConnectionFactory
from vm_manager.tests.factories import InstanceFactory, VolumeFactory
from vm_manager.tests.fakes import Fake, FakeNectar
from vm_manager.constants import ERROR
from vm_manager.utils.utils import get_nectar

from vm_manager.models import Instance, Volume, _create_hostname_id


class VolumeModelTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()
        self.feature = FeatureFactory.create(app_name='feature')
        self.desktop_type = DesktopTypeFactory.create(name='desktop',
                                                      feature=self.feature)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.models._create_hostname_id')
    def test_volume_save(self, mock_gen):
        mock_gen.return_value = "fnord"
        id = uuid.uuid4()
        volume = VolumeFactory.create(id=id, user=self.user,
                                      requesting_feature=self.feature)
        self.assertEquals("fnord", volume.hostname_id)
        mock_gen.assert_called_once()

        mock_gen.return_value = ERROR
        id = uuid.uuid4()
        with self.assertRaises(ValueError) as cm:
            volume = VolumeFactory.create(id=id, user=self.user,
                                          requesting_feature=self.feature)
        self.assertEqual("Could not assign random value to volume",
                         str(cm.exception))
        fake = get_nectar()
        fake.cinder.volumes.delete.assert_called_once_with(id)

    @patch('vm_manager.models.nanoid')
    def test_create_hostname_id(self, mock_nanoid):
        mock_nanoid.generate.return_value = "xxxxxx"
        volume = VolumeFactory.create(id=uuid.uuid4(), user=self.user,
                                      requesting_feature=self.feature)
        mock_nanoid.generate.assert_called_once()

        self.assertEqual(ERROR, _create_hostname_id())

        self.assertEqual(101, mock_nanoid.generate.call_count)

    def test_get_volume(self):
        self.assertIsNone(Volume.objects.get_volume(self.user,
                                                    self.desktop_type))
        volume = VolumeFactory.create(id=uuid.uuid4(), user=self.user,
                                      requesting_feature=self.feature)
        self.assertEqual(volume,
                         Volume.objects.get_volume(self.user,
                                                   self.desktop_type))
        volume = VolumeFactory.create(id=uuid.uuid4(), user=self.user,
                                      requesting_feature=self.feature)
        with self.assertRaises(Volume.MultipleObjectsReturned) as cm:
            Volume.objects.get_volume(self.user, self.desktop_type)
        self.assertEquals(
            f"Multiple current volumes found in the database with "
            f"user={self.user} and os={self.desktop_type.id}",
            str(cm.exception))


class InstanceModelTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()
        self.feature = FeatureFactory.create(app_name='feature')
        self.desktop_type = DesktopTypeFactory.create(name='desktop',
                                                      feature=self.feature)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    def test_get_ip_addr(self):
        fake_volume = VolumeFactory.create(
            id=uuid.uuid4(), user=self.user,
            requesting_feature=self.desktop_type.feature)
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        self.assertIsNone(fake_instance.ip_address)

        fake = get_nectar()
        mock_server = Mock()
        dummy_ip = "192.168.1.30"
        fake.nova.servers.get.return_value = Fake(
            addresses={
                'private': [
                    {
                        "OS-EXT-IPS-MAC:mac_addr": "00:0c:29:0d:11:74",
                        "OS-EXT-IPS:type": "fixed",
                        "addr": "192.168.1.30",
                        "version": 4
                    }
                ]
            }
        )

        ip = fake_instance.get_ip_addr()

        fake.nova.servers.get.assert_called_once_with(fake_instance.id)
        self.assertEqual(dummy_ip, ip)
        self.assertIsNotNone(fake_instance.ip_address)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    def test_get_status(self):
        fake = get_nectar()
        fake.nova.servers.get.return_value = Fake(status='testing')
        fake.nova.servers.get.reset_mock()

        fake_volume = VolumeFactory.create(
            id=uuid.uuid4(), user=self.user,
            requesting_feature=self.desktop_type.feature)
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        status = fake_instance.get_status()

        fake.nova.servers.get.assert_called_once_with(fake_instance.id)
        self.assertEqual('testing', status)

    def test_create_guac_connection(self):
        fake_volume = VolumeFactory.create(
            id=uuid.uuid4(), user=self.user,
            requesting_feature=self.desktop_type.feature)
        fake_guac_connection = GuacamoleConnectionFactory.create()
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume,
            guac_connection=fake_guac_connection,
            ip_address="10.0.0.1")

        with self.assertRaises(GuacamoleEntity.DoesNotExist):
            self.assertIsNone(GuacamoleEntity.objects.get(
                name=self.user.username))

        self.assertEqual(0,
                         GuacamoleConnectionParameter.objects.filter(
                             connection=fake_guac_connection).count())

        fake_instance.create_guac_connection()

        entity = GuacamoleEntity.objects.get(name=self.user.username)
        self.assertIsNotNone(entity)
        self.assertEqual(9,
                         GuacamoleConnectionParameter.objects.filter(
                             connection=fake_guac_connection).count())
        self.assertEqual(1,
                         GuacamoleConnectionPermission.objects.filter(
                             connection=fake_guac_connection,
                             entity=entity, permission='READ').count())

        # This is what create_guac_connection is used for ...
        url = fake_instance.get_url()
        self.assertTrue(url.startswith(f"{GUACAMOLE_URL}/#/client/"))

    def test_get_instance(self):
        self.assertIsNone(
            Instance.objects.get_instance(self.user, self.desktop_type))

        fake_volume = VolumeFactory.create(
            id=uuid.uuid4(), user=self.user,
            requesting_feature=self.desktop_type.feature)
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        self.assertEqual(
            fake_instance,
            Instance.objects.get_instance(self.user, self.desktop_type))

        # This is badness for testing
        another_fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        with self.assertRaises(Instance.MultipleObjectsReturned) as cm:
            Instance.objects.get_instance(self.user, self.desktop_type)
        self.assertEqual(f"Multiple current instances found in the database "
                         f"with user={self.user} and "
                         f"os={self.desktop_type.name}",
                         str(cm.exception))

    def test_get_instance_by_ip(self):
        ip_address = '10.0.0.2'
        self.assertIsNone(
            Instance.objects.get_instance_by_ip_address(
                ip_address, self.desktop_type.feature))

        fake_volume = VolumeFactory.create(
            id=uuid.uuid4(), user=self.user,
            requesting_feature=self.desktop_type.feature)
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume,
            ip_address=ip_address)

        self.assertEqual(
            fake_instance,
            Instance.objects.get_instance_by_ip_address(
                ip_address, self.desktop_type.feature))
