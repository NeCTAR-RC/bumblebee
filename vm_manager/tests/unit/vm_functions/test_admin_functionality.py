from datetime import datetime
from unittest.mock import Mock, patch

from django.utils.timezone import utc

from vm_manager.tests.fakes import FakeNectar
from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase

from vm_manager.constants import VM_OKAY, VM_DELETED, VM_WAITING, VM_SUPERSIZED
from vm_manager.models import VMStatus, Volume, Instance
from vm_manager.tests.factories import ResizeFactory
from vm_manager.utils.utils import NectarFactory
from vm_manager.vm_functions.admin_functionality import \
    admin_shelve_instance, admin_delete_instance_and_volume, \
    admin_delete_volume, admin_archive_volume, \
    admin_archive_instance_and_volume, admin_downsize_resize
from vm_manager.vm_functions.delete_vm import \
    archive_volume_worker, delete_vm_worker
from vm_manager.vm_functions.resize_vm import downsize_vm_worker
from vm_manager.vm_functions.shelve_vm import shelve_vm_worker


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
    @patch.object(NectarFactory, 'create', return_value=FakeNectar())
    def test_admin_archive_instance_and_volume(self, mock_cn, mock_archive,
                                               mock_rq):
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
    @patch.object(NectarFactory, 'create', return_value=FakeNectar())
    def test_admin_archive_instance_and_volume_2(self, mock_cn, mock_archive,
                                                 mock_rq):
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
    @patch.object(NectarFactory, 'create', return_value=FakeNectar())
    def test_admin_delete_volume(self, mock_cn, mock_delete, mock_rq):
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
    @patch.object(NectarFactory, 'create', return_value=FakeNectar())
    def test_admin_archive_volume(self, mock_cn, mock_archive, mock_rq):
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
    @patch.object(NectarFactory, 'create', return_value=FakeNectar())
    def test_admin_shelve_instance(self, mock_cn, mock_logger, mock_rq):
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
    @patch.object(NectarFactory, 'create', return_value=FakeNectar())
    def test_admin_downsize_instance(self, mock_cn, mock_logger, mock_rq):
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
