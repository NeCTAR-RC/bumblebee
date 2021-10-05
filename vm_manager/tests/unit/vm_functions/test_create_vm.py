import pdb

import uuid
import copy
from datetime import datetime, timedelta, timezone

from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase

from researcher_workspace.tests.factories import UserFactory
from researcher_desktop.utils.utils import get_desktop_type, desktops_feature

from vm_manager.tests.fakes import Fake, FakeServer, FakeVolume, FakeNectar
from vm_manager.tests.factories import InstanceFactory, VMStatusFactory, \
    VolumeFactory

from vm_manager.constants import VM_MISSING, VM_OKAY, VM_SHELVED, NO_VM
from vm_manager.models import VMStatus
from vm_manager.vm_functions.create_vm import launch_vm_worker, \
    wait_to_create_instance, _create_volume, _create_instance
from vm_manager.utils.utils import get_nectar


class CreateVMTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.FEATURE = desktops_feature()
        self.UBUNTU = get_desktop_type('ubuntu')
        self.CENTOS = get_desktop_type('centos')
        self.user = UserFactory.create()

    def _build_fake_volume(self, id=None):
        if id is None:
            id = uuid.UUID(bytes=b'\x15\x26\x37\x48' * 4)
        return VolumeFactory.create(
            id=id,
            user=self.user,
            image=self.UBUNTU.source_volume_id,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            flavor=self.UBUNTU.default_flavor.id)

    def _build_fake_vol_instance(self, volume_id=None, instance_id=None):
        if instance_id is None:
            instance_id = uuid.UUID(bytes=b'\x87\x65\x43\x21' * 4)
        fake_volume = self._build_fake_volume(id=volume_id)
        fake_instance = InstanceFactory.create(
            id=instance_id,
            boot_volume=fake_volume,
            user=self.user)
        return fake_volume, fake_instance

    def _build_fake_vol_inst_status(self, volume_id=None,
                                    instance_id=None,
                                    status=VM_OKAY):
        fake_volume, fake_instance = self._build_fake_vol_instance(
            volume_id=volume_id, instance_id=instance_id)
        fake_vmstatus = VMStatusFactory.create(
            user=self.user,
            instance=fake_instance,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            status=status)
        return fake_volume, fake_instance, fake_vmstatus

    @patch('vm_manager.vm_functions.create_vm._create_volume')
    @patch('vm_manager.vm_functions.create_vm.django_rq')
    def test_launch_vm_worker(self, mock_rq, mock_create):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_volume = self._build_fake_volume()
        mock_create.return_value = fake_volume

        result = launch_vm_worker(self.user, self.UBUNTU)
        self.assertIsNone(result)

        mock_create.assert_called_once_with(self.user, self.UBUNTU)
        mock_rq.get_scheduler.called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once()
        args = mock_scheduler.enqueue_in.call_args.args
        self.assertEqual(6, len(args))
        self.assertEqual(wait_to_create_instance, args[1])
        self.assertEqual(self.user, args[2])
        self.assertEqual(self.UBUNTU, args[3])
        self.assertEqual(fake_volume, args[4])

    @patch('vm_manager.vm_functions.create_vm._create_volume')
    @patch('vm_manager.vm_functions.create_vm.django_rq')
    def test_launch_vm_worker_instance_exists(self, mock_rq, mock_create):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_volume, _, _ = self._build_fake_vol_inst_status()
        mock_create.return_value = fake_volume

        with self.assertRaises(RuntimeWarning) as cm:
            launch_vm_worker(self.user, self.UBUNTU)
        self.assertEquals(f"A {self.UBUNTU.id} VM for {self.user.username} "
                          f"already exists",
                          str(cm.exception))

        mock_create.assert_not_called()
        mock_rq.get_scheduler.assert_not_called()
        mock_scheduler.enqueue_in.assert_not_called()

    @patch('vm_manager.vm_functions.create_vm._create_volume')
    @patch('vm_manager.vm_functions.create_vm.django_rq')
    def test_launch_vm_worker_instance_deleted(self, mock_rq, mock_create):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_volume, _, _ = self._build_fake_vol_inst_status(status=NO_VM)
        mock_create.return_value = fake_volume

        launch_vm_worker(self.user, self.UBUNTU)

        # The test_launch_vm_worker test does a more thorough job
        # of checking the mocks
        mock_create.assert_called_once()
        mock_rq.get_scheduler.assert_called_once()
        mock_scheduler.enqueue_in.assert_called_once()

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.create_vm._create_instance')
    def test_wait_to_create(self, mock_create_instance):
        fake_nectar = get_nectar()
        fake_volume, fake_instance, _ = self._build_fake_vol_inst_status()
        fake_nectar.cinder.volumes.get.return_value = FakeVolume(
            volume_id=fake_volume.id,
            status='available')
        mock_create_instance.return_value = fake_instance

        wait_to_create_instance(self.user, self.UBUNTU, fake_volume,
                                datetime.now(timezone.utc))

        fake_nectar.cinder.volumes.get.assert_called_once_with(
            volume_id=fake_volume.id)
        mock_create_instance.assert_called_once_with(
            self.user, self.UBUNTU, fake_volume)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.create_vm._create_instance')
    def test_wait_to_create_unshelve(self, mock_create_instance):
        fake_nectar = get_nectar()
        fake_volume, fake_instance, fake_status = \
            self._build_fake_vol_inst_status(status=VM_SHELVED)
        fake_volume.shelved = True
        fake_nectar.cinder.volumes.get.return_value = FakeVolume(
            volume_id=fake_volume.id,
            status='available')
        mock_create_instance.return_value = fake_instance

        wait_to_create_instance(self.user, self.UBUNTU, fake_volume,
                                datetime.now(timezone.utc))

        fake_nectar.cinder.volumes.get.assert_called_with(
            volume_id=fake_volume.id)
        mock_create_instance.assert_called_once_with(
            self.user, self.UBUNTU, fake_volume)

        self.assertFalse(fake_volume.shelved)

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(VM_OKAY, updated_status.status)

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
        fake_volume, _, _ = self._build_fake_vol_inst_status()

        result = _create_volume(self.user, self.UBUNTU)
        self.assertEqual(fake_volume, result)
        mock_get.assert_not_called()

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    def test_create_volume_deleted(self):
        fake_volume, _, _ = self._build_fake_vol_inst_status(status=NO_VM)

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
        fake_volume = self._build_fake_volume()

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
