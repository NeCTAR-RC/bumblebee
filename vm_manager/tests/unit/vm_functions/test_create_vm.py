from datetime import datetime, timedelta, timezone
import uuid

from unittest.mock import Mock, patch

import cinderclient
from django.conf import settings
from django.http import Http404

from researcher_desktop.tests.factories import AvailabilityZoneFactory

from vm_manager.tests.common import UUID_1
from vm_manager.tests.fakes import FakeServer, FakeVolume, FakeNectar
from vm_manager.tests.factories import VMStatusFactory
from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase

from vm_manager.constants import VM_OKAY, VM_SHELVED, NO_VM, \
    VM_WAITING, VOLUME_AVAILABLE, VOLUME_IN_USE
from vm_manager.models import VMStatus, Volume, Instance
from vm_manager.vm_functions.create_vm import launch_vm_worker, \
    wait_to_create_instance, _create_volume, _create_instance, \
    wait_for_instance_active, _get_source_volume_id, extend_instance
from vm_manager.utils.utils import get_nectar

utc = timezone.utc


class CreateVMTests(VMFunctionTestBase):

    @patch('vm_manager.vm_functions.create_vm._create_volume')
    @patch('vm_manager.vm_functions.create_vm.django_rq')
    @patch('vm_manager.vm_functions.create_vm.datetime')
    def test_launch_vm_worker(self, mock_datetime, mock_rq, mock_create):
        now = datetime.now(utc)
        mock_datetime.now.return_value = now
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_volume = self.build_fake_volume()
        mock_create.return_value = fake_volume

        result = launch_vm_worker(self.user, self.UBUNTU, self.zone)
        self.assertIsNone(result)

        mock_create.assert_called_once_with(self.user, self.UBUNTU, self.zone)
        mock_rq.get_scheduler.called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=5), wait_to_create_instance,
            self.user, self.UBUNTU, fake_volume, now)

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
                             "already exists",
                             str(cm.exception))

        mock_create.assert_not_called()
        mock_rq.get_scheduler.assert_not_called()
        mock_scheduler.enqueue_in.assert_not_called()

    @patch('vm_manager.vm_functions.create_vm._create_volume')
    @patch('vm_manager.vm_functions.create_vm.django_rq')
    def test_launch_vm_worker_volume_bad(self, mock_rq, mock_create):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        self.build_fake_volume()
        mock_create.return_value = None

        launch_vm_worker(self.user, self.UBUNTU, self.zone)

        mock_create.assert_called_once_with(self.user, self.UBUNTU, self.zone)
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
        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once()

    @patch('vm_manager.vm_functions.create_vm._create_instance')
    @patch('vm_manager.vm_functions.create_vm.django_rq')
    @patch('vm_manager.vm_functions.create_vm.datetime')
    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_wait_to_create(self, mock_get, mock_datetime,
                            mock_rq, mock_create_instance):
        now = datetime.now(utc)
        mock_datetime.now.return_value = now
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake = FakeNectar()
        fake_volume, fake_instance, fake_status = \
            self.build_fake_vol_inst_status()
        fake.cinder.volumes.get.return_value = FakeVolume(
            volume_id=fake_volume.id,
            status=VOLUME_AVAILABLE)
        mock_get.return_value = fake
        mock_create_instance.return_value = fake_instance

        wait_to_create_instance(self.user, self.UBUNTU, fake_volume,
                                datetime.now(utc))

        fake.cinder.volumes.get.assert_called_once_with(
            volume_id=fake_volume.id)
        mock_create_instance.assert_called_once_with(
            self.user, self.UBUNTU, fake_volume)
        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=5), wait_for_instance_active,
            self.user, self.UBUNTU, fake_instance, now)

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(VM_OKAY, updated_status.status)
        self.assertEqual(30, updated_status.status_progress)

    @patch('vm_manager.vm_functions.create_vm._create_instance')
    @patch('vm_manager.vm_functions.create_vm.django_rq')
    @patch('vm_manager.vm_functions.create_vm.datetime')
    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_wait_to_create_unshelve(self, mock_get, mock_datetime, mock_rq,
                                     mock_create_instance):
        now = datetime.now(utc)
        mock_datetime.now.return_value = now
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake = FakeNectar()
        fake_volume, fake_instance, fake_status = \
            self.build_fake_vol_inst_status(status=VM_SHELVED)
        fake_volume.shelved_at = now
        fake.cinder.volumes.get.return_value = FakeVolume(
            volume_id=fake_volume.id,
            status=VOLUME_AVAILABLE)
        mock_get.return_value = fake
        mock_create_instance.return_value = fake_instance

        wait_to_create_instance(self.user, self.UBUNTU, fake_volume, now)

        fake.cinder.volumes.get.assert_called_with(volume_id=fake_volume.id)
        mock_create_instance.assert_called_once_with(
            self.user, self.UBUNTU, fake_volume)

        self.assertIsNone(fake_volume.shelved_at)

        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=5), wait_for_instance_active,
            self.user, self.UBUNTU, fake_instance, now)
        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(VM_SHELVED, updated_status.status)
        self.assertEqual(30, updated_status.status_progress)

    @patch('vm_manager.vm_functions.create_vm.django_rq')
    @patch('vm_manager.vm_functions.create_vm._create_instance')
    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_wait_to_create_timeout(self, mock_get, mock_create_instance,
                                    mock_rq):
        fake = FakeNectar()
        fake_volume, _, fake_status = self.build_fake_vol_inst_status()
        fake.cinder.volumes.get.return_value = FakeVolume(
            volume_id=fake_volume.id,
            status=VOLUME_IN_USE)
        mock_get.return_value = fake

        with self.assertRaises(TimeoutError) as cm:
            time = (datetime.now(utc)
                    - timedelta(seconds=settings.VOLUME_CREATION_WAIT + 1))
            wait_to_create_instance(self.user, self.UBUNTU, fake_volume, time)
        self.assertEqual("Volume took too long to create", str(cm.exception))

        fake.cinder.volumes.get.assert_called_with(volume_id=fake_volume.id)
        mock_create_instance.assert_not_called()

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(NO_VM, updated_status.status)
        self.assertEqual(0, updated_status.status_progress)

        updated_volume = Volume.objects.get(id=fake_volume.id)
        self.assertEqual("Volume took too long to create",
                         updated_volume.error_message)
        self.assertIsNotNone(updated_volume.error_flag)
        mock_rq.get_scheduler.assert_not_called()

    @patch('vm_manager.vm_functions.create_vm.django_rq')
    @patch('vm_manager.vm_functions.create_vm._create_instance')
    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_wait_to_create_poll(self, mock_get, mock_create_instance,
                                 mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake = FakeNectar()
        fake_volume, _, fake_status = self.build_fake_vol_inst_status()
        fake.cinder.volumes.get.return_value = FakeVolume(
            volume_id=fake_volume.id,
            status=VOLUME_IN_USE)
        mock_get.return_value = fake

        start = datetime.now(utc) - timedelta(seconds=5)
        wait_to_create_instance(self.user, self.UBUNTU, fake_volume, start)

        fake.cinder.volumes.get.assert_called_with(
            volume_id=fake_volume.id)
        mock_create_instance.assert_not_called()
        mock_rq.get_scheduler.called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=5), wait_to_create_instance,
            self.user, self.UBUNTU, fake_volume, start)

    @patch('vm_manager.vm_functions.create_vm.generate_server_name')
    @patch('vm_manager.vm_functions.create_vm._get_source_volume_id')
    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_create_volume(self, mock_get_nectar, mock_get_id, mock_gen):
        mock_gen.return_value = "abcdef"
        mock_get_id.return_value = self.UBUNTU_source_volume_id
        VMStatusFactory.create(
            requesting_feature=self.FEATURE,
            operating_system=self.UBUNTU.id,
            user=self.user, status=NO_VM)
        fake = FakeNectar()
        fake.cinder.volumes.create.return_value = FakeVolume(id=UUID_1)
        mock_get_nectar.return_value = fake

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
        fake.cinder.volumes.create.assert_called_once_with(
            name="abcdef",
            source_volid=self.UBUNTU_source_volume_id,
            size=20,
            availability_zone=self.zone.name,
            metadata={'readonly': 'False'})
        fake.cinder.volumes.set_bootable.assert_called_once_with(
            volume=FakeVolume(id=result.id), flag=True)

        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.UBUNTU)
        self.assertEqual(NO_VM, vm_status.status)
        self.assertEqual(15, vm_status.status_progress)

    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    @patch('vm_manager.vm_functions.create_vm.logger')
    def test_create_volume_exists(self, mock_logger, mock_get):
        fake_volume, _, _ = self.build_fake_vol_inst_status()

        fake = FakeNectar()
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, availability_zone=self.zone.name,
            status=VOLUME_AVAILABLE)
        mock_get.return_value = fake

        self.assertIsNone(_create_volume(self.user, self.UBUNTU, self.zone))
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNone(volume.error_message)
        mock_logger.error.assert_called_once_with(
            f"VMstatus {VM_OKAY} inconsistent with existing {fake_volume} in "
            "_create_volume.  Needs manual cleanup.")
        fake.cinder.volumes.get.assert_called_once_with(fake_volume.id)

    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_create_volume_shelved(self, mock_get):
        fake_volume, _, _ = self.build_fake_vol_inst_status(status=VM_SHELVED)

        fake = FakeNectar()
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, availability_zone=self.zone.name,
            status=VOLUME_AVAILABLE)
        mock_get.return_value = fake

        self.assertEqual(fake_volume,
                         _create_volume(self.user, self.UBUNTU, self.zone))
        fake.cinder.volumes.get.assert_called_once_with(fake_volume.id)

    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    @patch('vm_manager.vm_functions.create_vm.logger')
    def test_create_volume_archived(self, mock_logger, mock_get):
        fake_volume, _, _ = self.build_fake_vol_inst_status(status=VM_SHELVED)

        fake = FakeNectar()
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, availability_zone=self.zone.name,
            status=VOLUME_AVAILABLE)
        mock_get.return_value = fake

        fake_volume.archived_at = datetime.now(utc)
        fake_volume.save()

        self.assertIsNone(_create_volume(self.user, self.UBUNTU, self.zone))
        fake.cinder.volumes.get.assert_called_once_with(fake_volume.id)
        mock_logger.error.assert_called_once_with(
            f"Cannot launch shelved volume marked as archived: {fake_volume}")

    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_create_volume_missing(self, mock_get):
        fake_volume, _, _ = self.build_fake_vol_inst_status()

        fake = FakeNectar()
        fake.cinder.volumes.get.side_effect = \
            cinderclient.exceptions.NotFound(code=42)
        mock_get.return_value = fake

        result = _create_volume(self.user, self.UBUNTU, self.zone)
        self.assertEqual(None, result)
        fake.cinder.volumes.get.assert_called_once_with(fake_volume.id)

    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    @patch('vm_manager.vm_functions.create_vm.logger')
    def test_create_volume_wrong_zone(self, mock_logger, mock_get):
        fake_volume, _, _ = self.build_fake_vol_inst_status()
        fake = FakeNectar()
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, availability_zone=self.zone.name,
            status=VOLUME_AVAILABLE)
        mock_get.return_value = fake

        other_zone = AvailabilityZoneFactory.create(
            name="different", zone_weight=100)
        self.assertIsNone(_create_volume(self.user, self.UBUNTU, other_zone))
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertEqual("Cinder volume in wrong AZ",
                         volume.error_message)
        mock_logger.error.assert_called_once_with(
            f"Cinder volume for {fake_volume} in wrong AZ. "
            "Needs manual cleanup")
        fake.cinder.volumes.get.assert_called_once_with(fake_volume.id)

    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_create_volume_deleted(self, mock_get):
        fake_volume, _, _ = self.build_fake_vol_inst_status(status=NO_VM)
        new_vol_id = str(uuid.uuid4())

        fake = FakeNectar()
        fake.cinder.volumes.list.return_value = [
            FakeVolume(name=f"{self.UBUNTU.image_name} [42]",
                       metadata={'nectar_build': '42'},
                       id=str(id))]
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, availability_zone=self.zone.name,
            status=VOLUME_AVAILABLE)
        fake.cinder.volumes.create.return_value = FakeVolume(id=new_vol_id)
        mock_get.return_value = fake

        self.assertIsNone(_create_volume(self.user, self.UBUNTU, self.zone))
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNone(volume.error_message)
        fake.cinder.volumes.create.assert_not_called()

    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_get_source_volume_id(self, mock_get):
        id = str(uuid.uuid4())
        fake = get_nectar()
        fake.cinder.volumes.list.reset_mock()
        fake.cinder.volumes.list.return_value = [
            FakeVolume(name=f"{self.UBUNTU.image_name} [42]",
                       metadata={'nectar_build': '42'},
                       id=id)]
        mock_get.return_value = fake

        self.assertEqual(id,
                         _get_source_volume_id(self.UBUNTU, self.zone))

        fake.cinder.volumes.list.assert_called_once_with(
            search_opts={'name~': self.UBUNTU.image_name,
                         'availability_zone': self.zone.name,
                         'status': VOLUME_AVAILABLE})

        fake.cinder.volumes.list.reset_mock()
        id2 = str(uuid.uuid4())
        fake.cinder.volumes.list.return_value = [
            FakeVolume(name=f"{self.UBUNTU.image_name} [42]",
                       metadata={'nectar_build': '42'},
                       id=id),
            FakeVolume(name=f"{self.UBUNTU.image_name} [43]",
                       metadata={'nectar_build': '43'},
                       id=id2)]
        self.assertEqual(id2,
                         _get_source_volume_id(self.UBUNTU, self.zone))

        fake.cinder.volumes.list.reset_mock()
        fake.cinder.volumes.list.return_value = []
        with self.assertRaises(RuntimeWarning):
            _get_source_volume_id(self.UBUNTU, self.zone)

    @patch('vm_manager.vm_functions.create_vm.generate_hostname')
    @patch('vm_manager.vm_functions.create_vm.generate_server_name')
    @patch('vm_manager.vm_functions.create_vm.generate_password')
    @patch('vm_manager.vm_functions.create_vm.render_to_string')
    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_create_instance(self, mock_get, mock_render, mock_gen_password,
                             mock_gen_server_name, mock_gen_hostname):
        mock_gen_hostname.return_value = "mullion"
        mock_gen_server_name.return_value = "foobar"
        mock_gen_password.return_value = "secret"
        mock_render.return_value = "RENDERED_USER_DATA"
        fake = FakeNectar()
        fake_volume = self.build_fake_volume()
        mock_get.return_value = fake

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

        expected_mapping = [{
            'source_type': "volume",
            'destination_type': 'volume',
            'delete_on_termination': False,
            'uuid': fake_volume.id,
            'boot_index': '0',
        }]

        fake.nova.servers.create.assert_called_once_with(
            name="foobar",
            image='',
            flavor=self.UBUNTU.default_flavor.id,
            userdata="RENDERED_USER_DATA",
            security_groups=self.UBUNTU.security_groups,
            block_device_mapping_v2=expected_mapping,
            nics=[{'net-id': self.zone.network_id}],
            availability_zone=self.zone.name,
            meta={'allow_user': self.user.username,
                  'environment': settings.ENVIRONMENT_NAME,
                  'requesting_feature': self.UBUNTU.feature.name},
            key_name=settings.OS_KEYNAME,
        )

    @patch('vm_manager.vm_functions.create_vm.django_rq')
    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    @patch('vm_manager.models.get_nectar')
    def test_wait_for_active_timeout(self, mock_get, mock_get_2, mock_rq):
        fake = FakeNectar()
        _, fake_instance, fake_status = self.build_fake_vol_inst_status()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status='BOOTING')
        mock_get.return_value = fake
        mock_get_2.return_value = fake

        time = (datetime.now(utc)
                - timedelta(seconds=settings.VOLUME_CREATION_WAIT + 1))
        wait_for_instance_active(
            self.user, self.UBUNTU, fake_instance, time)

        fake.nova.servers.get.assert_called_with(fake_instance.id)
        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(NO_VM, updated_status.status)
        updated_instance = Instance.objects.get(id=fake_instance.id)
        self.assertEqual("Instance took too long to launch",
                         updated_instance.error_message)
        self.assertIsNotNone(updated_instance.error_flag)
        mock_rq.get_scheduler.assert_not_called()

    @patch('vm_manager.vm_functions.create_vm.django_rq')
    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    @patch('vm_manager.models.get_nectar')
    def test_wait_for_active_poll(self, mock_get, mock_get_2, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake = FakeNectar()
        _, fake_instance, fake_status = self.build_fake_vol_inst_status()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status='BOOTING')
        mock_get.return_value = fake
        mock_get_2.return_value = fake

        start = datetime.now(utc) - timedelta(seconds=5)
        wait_for_instance_active(self.user, self.UBUNTU, fake_instance, start)

        fake.nova.servers.get.assert_called_with(fake_instance.id)
        mock_rq.get_scheduler.called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=5), wait_for_instance_active,
            self.user, self.UBUNTU, fake_instance, start)

    @patch('vm_manager.vm_functions.create_vm.django_rq')
    @patch('vm_manager.models.get_nectar')
    @patch('vm_manager.vm_functions.create_vm.get_nectar')
    def test_wait_for_active_success(self, mock_get, mock_get_2, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake = FakeNectar()
        _, fake_instance, fake_status = self.build_fake_vol_inst_status(
            status=VM_WAITING)
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status='ACTIVE')
        mock_get.return_value = fake
        mock_get_2.return_value = fake

        start = datetime.now(utc) - timedelta(seconds=5)
        wait_for_instance_active(self.user, self.UBUNTU, fake_instance, start)

        fake.nova.servers.get.assert_called_with(fake_instance.id)
        mock_rq.get_scheduler.assert_not_called()

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        # (Still waiting for the boot callback ...)
        self.assertEqual(VM_WAITING, updated_status.status)
        self.assertEqual(45, updated_status.status_progress)

    @patch('vm_manager.models.logger')
    @patch('vm_manager.vm_functions.create_vm.InstanceExpiryPolicy')
    def test_extend(self, mock_policy_class, mock_logger):
        mock_policy = Mock()
        mock_policy_class.return_value = mock_policy
        now = datetime.now(utc)
        new_expiry = now + timedelta(days=settings.BOOST_EXPIRY)
        mock_policy.new_expiry.return_value = new_expiry

        id = uuid.uuid4()
        with self.assertRaises(Http404):
            extend_instance(self.user, id, self.FEATURE)

        mock_logger.error.assert_called_with(
            f"Trying to get a vm that doesn't exist with vm_id: {id}, "
            f"called by {self.user}")

        _, fake_instance = self.build_fake_vol_instance()
        fake_instance.set_expires(now)
        self.assertEqual(
            str(fake_instance),
            extend_instance(self.user, fake_instance.id, self.FEATURE))
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.expiration)
        self.assertEqual(instance.expiration.expires, new_expiry)
