from datetime import datetime, timezone
from unittest.mock import call, Mock, patch

import cinderclient
import novaclient

from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase

from vm_manager.constants import VM_OKAY, VM_DELETED, VM_WAITING, \
    VM_ERROR, NO_VM, VM_SUPERSIZED, VM_SHELVED, \
    ACTIVE, SHUTDOWN, VOLUME_IN_USE, VOLUME_AVAILABLE, VOLUME_MAINTENANCE
from vm_manager.models import VMStatus, Volume, Instance, Resize
from vm_manager.tests.factories import ResizeFactory, VMStatusFactory
from vm_manager.tests.fakes import FakeNectar, FakeServer, FakeVolume
from vm_manager.vm_functions.admin_functionality import \
    admin_shelve_instance, admin_delete_instance_and_volume, \
    admin_delete_volume, admin_archive_volume, \
    admin_archive_instance_and_volume, admin_downsize_resize, \
    admin_check_vmstatus, admin_repair_volume_error, \
    admin_repair_instance_error
from vm_manager.vm_functions.delete_vm import delete_vm_worker
from vm_manager.vm_functions.resize_vm import downsize_vm_worker
from vm_manager.vm_functions.shelve_vm import shelve_vm_worker

utc = timezone.utc


class FakeReporter(Mock):
    def __init__(self):
        super().__init__()
        this = self
        self.errors = False
        self.repairs = False
        self.info = Mock()
        self.error = Mock(
            side_effect=lambda _: setattr(this, 'errors', True))
        self.repair = Mock(
            side_effect=lambda _: setattr(this, 'repairs', True))


class AdminVMTests(VMFunctionTestBase):

    @patch('vm_manager.vm_functions.admin_functionality.django_rq')
    @patch('vm_manager.vm_functions.admin_functionality.delete_volume')
    def test_admin_delete_instance_and_volume(self, mock_delete, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        mock_request = Mock()

        admin_delete_instance_and_volume(mock_request, fake_instance)
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.marked_for_deletion)
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNotNone(volume.marked_for_deletion)
        vm_status = VMStatus.objects.get(pk=fake_vmstatus.pk)
        self.assertEqual(VM_DELETED, vm_status.status)

        mock_rq.get_queue.assert_called_once_with('default')
        mock_queue.enqueue.assert_called_once_with(
            delete_vm_worker, fake_instance)
        mock_delete.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality.django_rq')
    @patch('vm_manager.vm_functions.admin_functionality.delete_volume')
    def test_admin_delete_instance_and_volume_2(self, mock_delete, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        mock_request = Mock()
        fake_instance.deleted = datetime.now(utc)

        admin_delete_instance_and_volume(mock_request, fake_instance)
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNone(instance.marked_for_deletion)
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNotNone(volume.marked_for_deletion)
        vm_status = VMStatus.objects.get(pk=fake_vmstatus.pk)
        self.assertEqual(VM_DELETED, vm_status.status)

        mock_rq.get_queue.assert_not_called()
        mock_delete.assert_called_once_with(fake_volume)

    @patch('vm_manager.vm_functions.admin_functionality.django_rq')
    @patch('vm_manager.vm_functions.admin_functionality.archive_volume_worker')
    def test_admin_archive_instance_and_volume(self, mock_archive, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        mock_request = Mock()

        admin_archive_instance_and_volume(mock_request, fake_instance)
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.marked_for_deletion)
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNotNone(volume.marked_for_deletion)
        vm_status = VMStatus.objects.get(pk=fake_vmstatus.pk)
        self.assertEqual(VM_DELETED, vm_status.status)

        mock_rq.get_queue.assert_called_once_with('default')
        mock_queue.enqueue.assert_called_once_with(
            delete_vm_worker, fake_instance, archive=True)
        mock_archive.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality.django_rq')
    @patch('vm_manager.vm_functions.admin_functionality.archive_volume_worker')
    def test_admin_archive_instance_and_volume_2(self, mock_archive, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        mock_request = Mock()
        fake_instance.deleted = datetime.now(utc)

        admin_archive_instance_and_volume(mock_request, fake_instance)
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNone(instance.marked_for_deletion)
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNotNone(volume.marked_for_deletion)
        vm_status = VMStatus.objects.get(pk=fake_vmstatus.pk)
        self.assertEqual(VM_DELETED, vm_status.status)

        mock_rq.get_queue.assert_not_called()
        mock_archive.assert_called_once_with(fake_volume, self.FEATURE)

    @patch('vm_manager.vm_functions.admin_functionality.django_rq')
    @patch('vm_manager.vm_functions.admin_functionality.delete_volume')
    def test_admin_delete_volume(self, mock_delete, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        mock_request = Mock()
        fake_instance.deleted = datetime.now(utc)

        admin_delete_volume(mock_request, fake_volume)
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNotNone(volume.marked_for_deletion)
        vm_status = VMStatus.objects.get(pk=fake_vmstatus.pk)
        self.assertEqual(VM_DELETED, vm_status.status)

        mock_rq.get_queue.assert_not_called()
        mock_delete.assert_called_once_with(fake_volume)

    @patch('vm_manager.vm_functions.admin_functionality.django_rq')
    @patch('vm_manager.vm_functions.admin_functionality.archive_volume_worker')
    def test_admin_archive_volume(self, mock_archive, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        mock_request = Mock()
        fake_instance.deleted = datetime.now(utc)
        fake_instance.shelved_at = datetime.now(utc)

        admin_archive_volume(mock_request, fake_volume)
        vm_status = VMStatus.objects.get(pk=fake_vmstatus.pk)
        self.assertEqual(VM_DELETED, vm_status.status)

        mock_rq.get_queue.assert_not_called()
        mock_archive.assert_called_once_with(fake_volume, self.FEATURE)

    @patch('vm_manager.vm_functions.admin_functionality.django_rq')
    @patch('vm_manager.vm_functions.admin_functionality.logger')
    def test_admin_shelve_instance(self, mock_logger, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        mock_request = Mock()

        admin_shelve_instance(mock_request, fake_instance)
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.marked_for_deletion)
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNone(volume.marked_for_deletion)
        vm_status = VMStatus.objects.get(pk=fake_vmstatus.pk)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertIsNotNone(vm_status.wait_time)

        mock_rq.get_queue.assert_called_once_with('default')
        mock_queue.enqueue.assert_called_once_with(
            shelve_vm_worker, fake_instance)

    @patch('vm_manager.vm_functions.admin_functionality.django_rq')
    @patch('vm_manager.vm_functions.admin_functionality.logger')
    def test_admin_downsize_instance(self, mock_logger, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SUPERSIZED)
        mock_request = Mock()
        fake_resize = ResizeFactory.create(instance=fake_instance)

        admin_downsize_resize(mock_request, fake_resize)
        vm_status = VMStatus.objects.get(pk=fake_vmstatus.pk)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertIsNotNone(vm_status.wait_time)

        mock_rq.get_queue.assert_called_once_with('default')
        mock_queue.enqueue.assert_called_once_with(
            downsize_vm_worker, fake_instance, self.UBUNTU)

    def _setup_fake_reporter(self, mock_reporter_class):
        fake_reporter = FakeReporter()
        mock_reporter_class.return_value = fake_reporter
        return fake_reporter

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_error(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_ERROR)
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_volume.id, status=ACTIVE)
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_IN_USE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_has_calls([
            call(f"VMStatus {fake_vmstatus.id} in state VM_Error "
                 f"for instance {fake_instance.id}"),
            call(f"Found nova instance {fake_instance.id} in state ACTIVE"),
            call(f"Found cinder volume {fake_volume.id} in state in-use")])
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_error_2(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_ERROR)
        fake = FakeNectar()
        fake.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(404)
        fake.cinder.volumes.get.side_effect = \
            cinderclient.exceptions.NotFound(404)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_has_calls([
            call(f"VMStatus {fake_vmstatus.id} in state VM_Error "
                 f"for instance {fake_instance.id}"),
            call(f"No nova instance {fake_instance.id}"),
            call(f"No cinder volume {fake_volume.id}")])
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_okay(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=ACTIVE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_not_called()
        fake_reporter.info.assert_called_once_with(
            f"VMStatus {fake_vmstatus.id} has no issues")

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_okay_shutdown(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=SHUTDOWN)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_called_with(
            f"Found nova instance {fake_instance.id} in state {SHUTDOWN} "
            f"for a {VM_OKAY} vmstatus")
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_okay_missing(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        fake = FakeNectar()
        fake.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(404)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_called_with(
            f"Missing nova instance {fake_instance.id} "
            f"for a {VM_OKAY} vmstatus")
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_okay_with_resize(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        _ = ResizeFactory.create(instance=fake_instance)
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=ACTIVE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_called_with(
            f"Unreverted Resize for normal sized instance {fake_instance.id}")
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_supersized(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SUPERSIZED)
        _ = ResizeFactory.create(instance=fake_instance)
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=ACTIVE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_not_called()
        fake_reporter.info.assert_called_with(
            f"VMStatus {fake_vmstatus.id} has no issues")

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_supersized_missing_resize(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SUPERSIZED)
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=ACTIVE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_called_with(
            f"Missing Resize for supersized instance {fake_instance.id}")
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_supersized_no_resize(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SUPERSIZED)
        _ = ResizeFactory.create(instance=fake_instance,
                                 reverted=datetime.now(utc))
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=ACTIVE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_called_with(
            f"Reverted Resize for supersized instance {fake_instance.id}")
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_not_current(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_OKAY)
        fake = FakeNectar()
        _ = VMStatusFactory.create(
            instance=fake_instance,
            status=VM_ERROR,
            requesting_feature_id=fake_vmstatus.requesting_feature_id,
            user_id=fake_vmstatus.user_id,
            created=datetime.now(utc))

        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=ACTIVE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_called_once_with(
            f"VMStatus {fake_vmstatus.id} for "
            f"volume {fake_volume.id} instance {fake_instance.id} "
            "is not current.")
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_shelved(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        _ = ResizeFactory.create(instance=fake_instance)
        fake = FakeNectar()
        fake.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(404)
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_AVAILABLE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_not_called()
        fake_reporter.info.assert_called_with(
            f"VMStatus {fake_vmstatus.id} has no issues")

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_shelved_2(
            self, mock_get, mock_reporter_class):
        # Unexpected Instance
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        _ = ResizeFactory.create(instance=fake_instance)
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=ACTIVE)
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_IN_USE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_has_calls([
            call(f"Found nova instance {fake_instance.id} in state {ACTIVE} "
                 f"for a {VM_SHELVED} vmstatus"),
            call(f"Cinder volume {fake_volume.id} is in state "
                 f"{VOLUME_IN_USE} for a {VM_SHELVED} vmstatus")])
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_shelved_3(
            self, mock_get, mock_reporter_class):
        # Unexpected in-use volume
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        _ = ResizeFactory.create(instance=fake_instance)
        fake = FakeNectar()
        fake.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(404)
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_IN_USE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_called_with(
            f"Cinder volume {fake_volume.id} is in state {VOLUME_IN_USE} "
            f"for a {VM_SHELVED} vmstatus")
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_vmstatus_shelved_4(
            self, mock_get, mock_reporter_class):
        # Unexpected missing volume
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        _ = ResizeFactory.create(instance=fake_instance)
        fake = FakeNectar()
        fake.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(404)
        fake.cinder.volumes.get.side_effect = \
            cinderclient.exceptions.NotFound(404)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        admin_check_vmstatus(mock_request, fake_vmstatus)

        fake_reporter.error.assert_called_with(
            f"Cinder volume {fake_volume.id} is missing "
            f"for a {VM_SHELVED} vmstatus")
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_repair_volume(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        fake = FakeNectar()
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_AVAILABLE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        self.assertEqual(True,
                         admin_repair_volume_error(mock_request, fake_volume))

        fake_reporter.error.assert_not_called()
        fake_reporter.info.assert_called_with(
            f"Volume {fake_volume.id} has no issues")

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_repair_volume_cleared(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        fake_volume.error("Cheezeburger")
        fake = FakeNectar()
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_AVAILABLE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        self.assertEqual(True,
                         admin_repair_volume_error(mock_request, fake_volume))

        fake_reporter.error.assert_not_called()
        fake_reporter.repair.assert_called_with(
            f"Cleared error for volume {fake_volume.id}")
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNone(volume.error_flag)
        self.assertIsNone(volume.error_message)

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_repair_volume_missing_cleared(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        fake_volume.error("Cheezeburger")
        fake = FakeNectar()
        fake.cinder.volumes.get.side_effect = \
            cinderclient.exceptions.NotFound(404)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        self.assertEqual(True,
                         admin_repair_volume_error(mock_request, fake_volume))

        fake_reporter.error.assert_not_called()
        fake_reporter.repair.assert_called_once_with(
            f"Cinder volume {fake_volume.id} is missing. "
            "Recording desktop as deleted.")
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNotNone(volume.error_flag)
        self.assertIsNotNone(volume.error_message)
        self.assertIsNotNone(volume.deleted)

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_repair_volume_maint(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        fake = FakeNectar()
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_MAINTENANCE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        self.assertEqual(False,
                         admin_repair_volume_error(mock_request, fake_volume))

        fake_reporter.error.assert_called_once_with(
            f"Cinder volume {fake_volume.id} is in unexpected state "
            f"{VOLUME_MAINTENANCE}. Manual cleanup required.")
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_repair_instance(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=ACTIVE)
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_IN_USE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        self.assertEqual(True,
                         admin_repair_instance_error(mock_request,
                                                     fake_instance))

        fake_reporter.error.assert_not_called()
        fake_reporter.info.assert_has_calls([
            call(f"Volume {fake_volume.id} has no issues"),
            call(f"Instance {fake_instance.id} has no issues")])

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_repair_instance_maint_volume(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=ACTIVE)
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_MAINTENANCE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        self.assertEqual(False,
                         admin_repair_instance_error(mock_request,
                                                     fake_instance))

        fake_reporter.error.assert_has_calls([
            call(f"Cinder volume {fake_volume.id} is in unexpected "
                 f"state {VOLUME_MAINTENANCE}. Manual cleanup required."),
            call(f"Volume error for instance {fake_instance.id} "
                 "must be dealt with first.")])
        fake_reporter.repair.assert_not_called()
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_repair_instance_deleted_volume(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        fake_volume.deleted = datetime.now(utc)
        fake_volume.save()
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=SHUTDOWN)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        self.assertEqual(False,
                         admin_repair_instance_error(mock_request,
                                                     fake_instance))

        fake_reporter.error.assert_called_once_with(
            f"Nova instance {fake_instance.id} still exists for "
            f"deleted volume {fake_volume.id}. Manual cleanup required.")
        fake_reporter.repair.assert_not_called()
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_repair_instance_shutdown(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        fake = FakeNectar()
        fake.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=SHUTDOWN)
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_IN_USE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        self.assertEqual(False,
                         admin_repair_instance_error(mock_request,
                                                     fake_instance))

        fake_reporter.error.assert_called_once_with(
            f"Nova instance {fake_instance.id} is in "
            f"unexpected state {SHUTDOWN}. Manual cleanup required.")
        fake_reporter.repair.assert_not_called()
        fake_reporter.info.assert_called_with(
            f"Volume {fake_volume.id} has no issues")

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_repair_instance_missing_volume_bad(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        fake = FakeNectar()
        fake.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(404)
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_MAINTENANCE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        self.assertEqual(False,
                         admin_repair_instance_error(mock_request,
                                                     fake_instance))

        fake_reporter.error.assert_has_calls([
            call(f"Cinder volume {fake_volume.id} is in unexpected "
                 f"state {VOLUME_MAINTENANCE}. Manual cleanup required."),
            call(f"Volume error for instance {fake_instance.id} "
                 "must be dealt with first.")])
        fake_reporter.repair.assert_not_called()
        fake_reporter.info.assert_not_called()

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_repair_instance_missing_autoshelve(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        fake_instance.error("Something bad happened")
        fake_volume.error("Something bad happened")
        fake = FakeNectar()
        fake.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(404)
        fake.cinder.volumes.get.return_value = FakeVolume(
            id=fake_volume.id, status=VOLUME_AVAILABLE)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        self.assertTrue(admin_repair_instance_error(
            mock_request, fake_instance))

        fake_reporter.error.assert_not_called()
        fake_reporter.repair.assert_has_calls([
            call(f"Cleared error for volume {fake_volume.id}"),
            call(f"Nova instance {fake_instance.id} missing. "
                 "Recording desktop as shelved.")])
        fake_reporter.info.assert_not_called()

        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNone(volume.deleted)
        self.assertIsNone(volume.error_flag)
        self.assertIsNone(volume.error_message)
        self.assertIsNotNone(volume.shelved_at)
        self.assertIsNotNone(volume.expiration)
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.deleted)
        self.assertIsNotNone(instance.error_flag)
        self.assertIsNotNone(instance.error_message)
        vmstatus = VMStatus.objects.get(pk=fake_vmstatus.pk)
        self.assertEqual(VM_SHELVED, vmstatus.status)

    @patch('vm_manager.vm_functions.admin_functionality._Reporter')
    @patch('vm_manager.vm_functions.admin_functionality.get_nectar')
    def test_admins_check_repair_instance_missing_autodelete(
            self, mock_get, mock_reporter_class):
        fake_volume, fake_instance, fake_vmstatus = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_SHELVED)
        fake_instance.error("Something bad happened")
        fake_volume.error("Something bad happened")
        fake_resize = ResizeFactory.create(instance=fake_instance)
        fake = FakeNectar()
        fake.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(404)
        fake.cinder.volumes.get.side_effect = \
            cinderclient.exceptions.NotFound(404)
        mock_get.return_value = fake
        mock_request = Mock()
        fake_reporter = self._setup_fake_reporter(mock_reporter_class)

        self.assertTrue(admin_repair_instance_error(
            mock_request, fake_instance))

        fake_reporter.error.assert_not_called()
        fake_reporter.repair.assert_has_calls([
            call(f"Cinder volume {fake_volume.id} is missing. "
                 "Recording desktop as deleted."),
            call(f"Reverting resize for instance {fake_instance.id}."),
            call(f"Recording instance {fake_instance.id} as deleted.")])

        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNotNone(volume.deleted)
        self.assertIsNotNone(volume.error_flag)
        self.assertIsNotNone(volume.error_message)
        self.assertIsNone(volume.shelved_at)
        self.assertIsNone(volume.expiration)
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.deleted)
        self.assertIsNotNone(instance.error_flag)
        self.assertIsNotNone(instance.error_message)
        vmstatus = VMStatus.objects.get(pk=fake_vmstatus.pk)
        self.assertEqual(NO_VM, vmstatus.status)
        resize = Resize.objects.get(pk=fake_resize.pk)
        self.assertIsNotNone(resize.reverted)
