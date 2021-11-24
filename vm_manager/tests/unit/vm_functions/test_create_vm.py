import copy
from datetime import datetime, timedelta, timezone
import uuid

from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase

from researcher_workspace.tests.factories import UserFactory
from researcher_desktop.tests.factories import AvailabilityZoneFactory
from researcher_desktop.utils.utils import get_desktop_type, desktops_feature

from vm_manager.tests.common import UUID_1, UUID_2, UUID_3, UUID_4
from vm_manager.tests.fakes import Fake, FakeServer, FakeVolume, FakeNectar
from vm_manager.tests.factories import InstanceFactory, VMStatusFactory, \
    VolumeFactory
from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase

from vm_manager.constants import VM_MISSING, VM_OKAY, VM_SHELVED, NO_VM, \
    VOLUME_CREATION_TIMEOUT
from vm_manager.models import VMStatus, Volume
from vm_manager.vm_functions.create_vm import launch_vm_worker, \
    wait_to_create_instance, _create_volume, _create_instance, \
    _get_source_volume_id
from vm_manager.utils.utils import get_nectar


class CreateVMTests(VMFunctionTestBase):

    @patch('vm_manager.vm_functions.create_vm._create_volume')
    @patch('vm_manager.vm_functions.create_vm.django_rq')
    def test_launch_vm_worker(self, mock_rq, mock_create):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_volume = self.build_fake_volume()
        mock_create.return_value = fake_volume

        result = launch_vm_worker(self.user, self.UBUNTU, self.zone)
        self.assertIsNone(result)

        mock_create.assert_called_once_with(self.user, self.UBUNTU, self.zone)
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
        fake_volume, _, _ = self.build_fake_vol_inst_status()
        mock_create.return_value = fake_volume

        with self.assertRaises(RuntimeWarning) as cm:
            launch_vm_worker(self.user, self.UBUNTU, self.zone)
            self.assertEqual(f"A {self.UBUNTU.id} VM for {self.user.username} "
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
        fake_volume, _, _ = self.build_fake_vol_inst_status(status=NO_VM)
        mock_create.return_value = fake_volume

        launch_vm_worker(self.user, self.UBUNTU, self.zone)

        # The test_launch_vm_worker test does a more thorough job
        # of checking the mocks
        mock_create.assert_called_once()
        mock_rq.get_scheduler.assert_called_once()
        mock_scheduler.enqueue_in.assert_called_once()

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.create_vm._create_instance')
    def test_wait_to_create(self, mock_create_instance):
        fake_nectar = get_nectar()
        fake_volume, fake_instance, _ = self.build_fake_vol_inst_status()
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
            self.build_fake_vol_inst_status(status=VM_SHELVED)
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
    @patch('vm_manager.vm_functions.create_vm._create_instance')
    def test_wait_to_create_timeout(self, mock_create_instance):
        fake_nectar = get_nectar()
        fake_volume, _, fake_status = self.build_fake_vol_inst_status()
        fake_nectar.cinder.volumes.get.return_value = FakeVolume(
            volume_id=fake_volume.id,
            status='unavailable')

        with self.assertRaises(TimeoutError) as cm:
            time = (datetime.now(timezone.utc)
                    - timedelta(seconds=VOLUME_CREATION_TIMEOUT + 1))
            wait_to_create_instance(self.user, self.UBUNTU, fake_volume, time)
        self.assertEqual("Volume took too long to create", str(cm.exception))

        fake_nectar.cinder.volumes.get.assert_called_with(
            volume_id=fake_volume.id)
        mock_create_instance.assert_not_called()

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(NO_VM, updated_status.status)

        updated_volume = Volume.objects.get(id=fake_volume.id)
        self.assertEqual("Volume took too long to create",
                         updated_volume.error_message)
        self.assertIsNotNone(updated_volume.error_flag)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.create_vm.django_rq')
    @patch('vm_manager.vm_functions.create_vm._create_instance')
    def test_wait_to_create_poll(self, mock_create_instance, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_nectar = get_nectar()
        fake_volume, _, fake_status = self.build_fake_vol_inst_status()
        fake_nectar.cinder.volumes.get.return_value = FakeVolume(
            volume_id=fake_volume.id,
            status='unavailable')

        wait_to_create_instance(self.user, self.UBUNTU, fake_volume,
                                datetime.now(timezone.utc)
                                - timedelta(seconds=5))

        fake_nectar.cinder.volumes.get.assert_called_with(
            volume_id=fake_volume.id)
        mock_create_instance.assert_not_called()
        mock_rq.get_scheduler.called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once()
        args = mock_scheduler.enqueue_in.call_args.args
        self.assertEqual(6, len(args))
        self.assertEqual(wait_to_create_instance, args[1])
        self.assertEqual(self.user, args[2])
        self.assertEqual(self.UBUNTU, args[3])
        self.assertEqual(fake_volume, args[4])

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.create_vm.generate_server_name')
    @patch('vm_manager.vm_functions.create_vm._get_source_volume_id')
    def test_create_volume(self, mock_get_id, mock_gen):
        mock_gen.return_value = "abcdef"
        mock_get_id.return_value = self.UBUNTU_source_volume_id
        result = _create_volume(self.user, self.UBUNTU, self.zone)

        self.assertIsNotNone(result)
        self.assertEqual(UUID_1, result.id)
        self.assertEqual(self.user, result.user)
        self.assertEqual(self.UBUNTU_source_volume_id, result.image)
        self.assertEqual(self.UBUNTU.id, result.operating_system)
        self.assertEqual(self.UBUNTU.feature, result.requesting_feature)
        self.assertEqual(self.UBUNTU.default_flavor.id, result.flavor)

        mock_gen.assert_called_once_with(self.user.username, self.UBUNTU.id)
        mock_get_id.assert_called_once_with(self.UBUNTU, self.zone)
        fake = get_nectar()
        fake.cinder.volumes.create.assert_called_once_with(
            name="abcdef",
            source_volid=self.UBUNTU_source_volume_id,
            size=fake.VM_PARAMS['size'],
            availability_zone=self.zone.name,
            metadata=fake.VM_PARAMS['metadata_volume'])
        fake.cinder.volumes.set_bootable.assert_called_once_with(
            volume=FakeVolume(id=result.id), flag=True)

    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_create_volume_exists(self, mock_get):
        fake_volume, _, _ = self.build_fake_vol_inst_status()

        result = _create_volume(self.user, self.UBUNTU, self.zone)
        self.assertEqual(fake_volume, result)
        mock_get.assert_not_called()

    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_create_volume_wrong_zone(self, mock_get):
        fake_volume, _, _ = self.build_fake_vol_inst_status()

        other_zone = AvailabilityZoneFactory.create(
            name="different", zone_weight=100)
        with self.assertRaises(RuntimeWarning):
            _create_volume(self.user, self.UBUNTU, other_zone)
        mock_get.assert_not_called()

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    def test_create_volume_deleted(self):
        fake_volume, _, _ = self.build_fake_vol_inst_status(status=NO_VM)

        fake = get_nectar()
        fake.cinder.volumes.create.reset_mock()
        fake.cinder.volumes.list.return_value = [
            FakeVolume(name=f"{self.UBUNTU.image_name} [42]",
                       id=str(id))]

        result = _create_volume(self.user, self.UBUNTU, self.zone)
        self.assertNotEqual(fake_volume, result)
        self.assertEqual(UUID_1, result.id)

        fake.cinder.volumes.create.assert_called_once()

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    def test_get_source_volume_id(self):
        id = uuid.uuid4()
        fake = get_nectar()
        fake.cinder.volumes.list.reset_mock()
        fake.cinder.volumes.list.return_value = [
            FakeVolume(name=f"{self.UBUNTU.image_name} [42]",
                       id=str(id))]

        self.assertEqual(str(id),
                         _get_source_volume_id(self.UBUNTU, self.zone))

        fake.cinder.volumes.list.assert_called_once_with(
            search_opts={'name~': self.UBUNTU.image_name,
                         'availability_zone': self.zone.name})

        fake.cinder.volumes.list.reset_mock()
        fake.cinder.volumes.list.return_value = []
        with self.assertRaises(RuntimeWarning):
            _get_source_volume_id(self.UBUNTU, self.zone)

        fake.cinder.volumes.list.reset_mock()
        fake.cinder.volumes.list.return_value = [
            FakeVolume(name=f"{self.UBUNTU.image_name} [42]",
                       id=str(id)),
            FakeVolume(name=f"{self.UBUNTU.image_name} [43]",
                       id=str(id))]
        with self.assertRaises(RuntimeWarning):
            _get_source_volume_id(self.UBUNTU, self.zone)

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
        fake_volume = self.build_fake_volume()

        result = _create_instance(self.user, self.UBUNTU, fake_volume)

        self.assertIsNotNone(result)
        self.assertEqual(UUID_1, result.id)
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
            availability_zone=self.zone.name,
            meta={'allow_user': self.user.username,
                  'environment': settings.ENVIRONMENT_NAME,
                  'requesting_feature': self.UBUNTU.feature.name}
        )
