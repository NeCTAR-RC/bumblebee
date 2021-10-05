import pdb

import uuid
import copy

from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase

from researcher_workspace.tests.factories import UserFactory
from researcher_desktop.utils.utils import get_desktop_type, desktops_feature

from vm_manager.tests.fakes import Fake, FakeServer, FakeVolume, FakeNectar
from vm_manager.tests.factories import InstanceFactory, VMStatusFactory, \
    VolumeFactory

from vm_manager.constants import VM_MISSING, NO_VM
from vm_manager.vm_functions.create_vm import _create_volume, _create_instance
from vm_manager.utils.utils import get_nectar


class CreateVMTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.FEATURE = desktops_feature()
        self.UBUNTU = get_desktop_type('ubuntu')
        self.CENTOS = get_desktop_type('centos')
        self.user = UserFactory.create()

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.create_vm.generate_server_name')
    def test_create_volume(self, mock_gen):
        mock_gen.return_value = "abcdef"
        result = _create_volume(self.user, self.UBUNTU)

        self.assertIsNotNone(result)
        self.assertEqual(uuid.UUID(bytes=b'\x12\x34\x56\x78' * 4), result.id)
        self.assertEqual(self.user, result.user)
        self.assertEqual(self.UBUNTU.source_volume_id, result.image)
        self.assertEqual(self.UBUNTU.id, result.operating_system)
        self.assertEqual(self.UBUNTU.feature, result.requesting_feature)
        self.assertEqual(self.UBUNTU.default_flavor.id, result.flavor)

        mock_gen.assert_called_once_with(self.user.username, self.UBUNTU.id)
        fake = get_nectar()
        fake.cinder.volumes.create.assert_called_once_with(
            name="abcdef",
            source_volid=self.UBUNTU.source_volume_id,
            size=fake.VM_PARAMS['size'],
            availability_zone=fake.VM_PARAMS['availability_zone_volume'],
            metadata=fake.VM_PARAMS['metadata_volume'])
        fake.cinder.volumes.set_bootable.assert_called_once_with(
            volume=FakeVolume(id=result.id), flag=True)

    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_create_volume_exists(self, mock_get):
        fake_volume = VolumeFactory.create(
            id=uuid.UUID(bytes=b'\x13\x24\x57\x68' * 4),
            user=self.user,
            image=self.UBUNTU.source_volume_id,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            flavor=self.UBUNTU.default_flavor.id)
        fake_instance = InstanceFactory.create(
            boot_volume=fake_volume,
            user=self.user)
        fake_vmstatus = VMStatusFactory.create(
            user=self.user,
            instance=fake_instance,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            status=VM_MISSING)

        result = _create_volume(self.user, self.UBUNTU)
        self.assertEqual(fake_volume, result)
        mock_get.assert_not_called()

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    def test_create_volume_deleted(self):
        fake_volume = VolumeFactory.create(
            id=uuid.UUID(bytes=b'\x13\x24\x57\x68' * 4),
            user=self.user,
            image=self.UBUNTU.source_volume_id,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            flavor=self.UBUNTU.default_flavor.id)
        fake_instance = InstanceFactory.create(
            id=uuid.UUID(bytes=b'\x87\x65\x43\x21' * 4),
            boot_volume=fake_volume,
            user=self.user)
        fake_vmstatus = VMStatusFactory.create(
            user=self.user,
            instance=fake_instance,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            status=NO_VM)

        fake = get_nectar()
        fake.cinder.volumes.create.reset_mock()

        result = _create_volume(self.user, self.UBUNTU)
        self.assertNotEqual(fake_volume, result)
        self.assertEqual(uuid.UUID(bytes=b'\x12\x34\x56\x78' * 4), result.id)

        fake.cinder.volumes.create.assert_called_once()

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.create_vm.generate_hostname')
    @patch('vm_manager.vm_functions.create_vm.generate_password')
    @patch('vm_manager.vm_functions.create_vm.render_to_string')
    def test_create_instance(self, mock_render, mock_gen_password,
                             mock_gen_hostname):
        mock_gen_hostname.return_value = "mullion"
        mock_gen_password.return_value = "secret"
        mock_render.return_value = "RENDERED_USER_DATA"
        fake = get_nectar()
        fake_volume = VolumeFactory.create(
            id=uuid.UUID(bytes=b'\x15\x26\x37\x48' * 4),
            user=self.user,
            image=self.UBUNTU.source_volume_id,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            flavor=self.UBUNTU.default_flavor.id)

        result = _create_instance(self.user, self.UBUNTU, fake_volume)

        self.assertIsNotNone(result)
        self.assertEqual(uuid.UUID(bytes=b'\x12\x34\x56\x78' * 4), result.id)
        self.assertEqual(self.user, result.user)
        self.assertEqual(fake_volume, result.boot_volume)
        self.assertEqual("vdiuser", result.username)
        self.assertEqual("secret", result.password)
        self.assertIsNotNone(result.guac_connection)

        mock_gen_password.assert_called_once()
        mock_gen_hostname.assert_called_once()

        fake = get_nectar()
        expected_mapping = copy.deepcopy(
            fake.VM_PARAMS['block_device_mapping'])
        expected_mapping[0]["uuid"] = fake_volume.id

        fake.nova.servers.create.assert_called_once_with(
            userdata="RENDERED_USER_DATA",
            security_groups=self.UBUNTU.security_groups,
            key_name=settings.OS_KEYNAME,
            name="mullion",
            flavor=self.UBUNTU.default_flavor.id,
            image='',
            block_device_mapping_v1=None,
            block_device_mapping_v2=expected_mapping,
            nics=fake.VM_PARAMS['list_net'],
            availability_zone=fake.VM_PARAMS['availability_zone_server'],
            meta={'allow_user': self.user.username,
                  'environment': settings.ENVIRONMENT_NAME,
                  'requesting_feature': self.UBUNTU.feature.name}
        )
