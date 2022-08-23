from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import novaclient

from django.utils.timezone import utc

from guacamole.tests.factories import GuacamoleConnectionFactory
from vm_manager.constants import ACTIVE, SHUTDOWN, RESCUE, \
    VM_OKAY, VM_WAITING, VM_ERROR, VM_SHELVED, VM_SUPERSIZED, \
    FORCED_SHELVE_WAIT_SECONDS, INSTANCE_CHECK_SHUTOFF_RETRY_COUNT, \
    INSTANCE_DELETION_RETRY_COUNT, INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME, \
    INSTANCE_DELETION_RETRY_WAIT_TIME, \
    WF_RETRY, WF_SUCCESS, WF_CONTINUE
from vm_manager.models import VMStatus, Instance, Volume
from vm_manager.tests.common import UUID_4
from vm_manager.tests.fakes import FakeNectar, FakeServer
from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase
from vm_manager.utils.utils import get_nectar
from vm_manager.vm_functions.shelve_vm import shelve_vm_worker, \
    shelve_expired_vm, _confirm_instance_deleted, \
    _check_instance_is_shutoff_and_delete


class ShelveVMTests(VMFunctionTestBase):

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.shelve_vm.django_rq')
    def test_shelve_vm_worker_wrong_state(self, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        # (Could be any state apart from ACTIVE or SHUTDOWN)
        fake_nectar.nova.servers.get.return_value = FakeServer(status=RESCUE)

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99', status=VM_OKAY)
        fake_guac = GuacamoleConnectionFactory.create(instance=fake_instance)
        fake_instance.guac_connection = fake_guac

        self.assertEqual(WF_RETRY, shelve_vm_worker(fake_instance))

        fake_nectar.nova.servers.get.assert_called_once_with(UUID_4)
        mock_rq.get_scheduler.assert_not_called()
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.error_message)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.shelve_vm.django_rq')
    def test_shelve_vm_worker_missing(self, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(code=42)  # the code is ignored

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99', status=VM_OKAY)
        fake_guac = GuacamoleConnectionFactory.create(instance=fake_instance)
        fake_instance.guac_connection = fake_guac

        self.assertEqual(WF_SUCCESS, shelve_vm_worker(fake_instance))

        fake_nectar.nova.servers.get.assert_called_once_with(UUID_4)
        mock_rq.get_scheduler.assert_not_called()
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.error_message)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.shelve_vm.django_rq')
    def test_shelve_vm_worker_shutdown(self, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        now = datetime.now(utc)
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.return_value = FakeServer(status=SHUTDOWN)
        fake_nectar.nova.servers.stop = Mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99', status=VM_OKAY)
        fake_guac = GuacamoleConnectionFactory.create(instance=fake_instance)
        fake_instance.guac_connection = fake_guac

        self.assertEqual(WF_CONTINUE, shelve_vm_worker(fake_instance))

        fake_nectar.nova.servers.get.assert_called_once_with(UUID_4)
        fake_nectar.nova.servers.stop.assert_not_called()

        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertEqual(33, vm_status.status_progress)
        self.assertTrue(vm_status.wait_time >= now + timedelta(
            seconds=FORCED_SHELVE_WAIT_SECONDS))
        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
            _check_instance_is_shutoff_and_delete, fake_instance,
            INSTANCE_CHECK_SHUTOFF_RETRY_COUNT,
            _confirm_instance_deleted,
            (fake_instance, INSTANCE_DELETION_RETRY_COUNT))

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.shelve_vm.django_rq')
    def test_shelve_vm_worker(self, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        now = datetime.now(utc)
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.return_value = FakeServer(status=ACTIVE)
        fake_nectar.nova.servers.stop = Mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99', status=VM_OKAY)
        fake_guac = GuacamoleConnectionFactory.create(instance=fake_instance)
        fake_instance.guac_connection = fake_guac

        self.assertEqual(WF_CONTINUE, shelve_vm_worker(fake_instance))

        fake_nectar.nova.servers.get.assert_called_once_with(UUID_4)
        fake_nectar.nova.servers.stop.assert_called_once_with(UUID_4)

        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertEqual(33, vm_status.status_progress)
        self.assertTrue(vm_status.wait_time >= now + timedelta(
            seconds=FORCED_SHELVE_WAIT_SECONDS))
        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
            _check_instance_is_shutoff_and_delete, fake_instance,
            INSTANCE_CHECK_SHUTOFF_RETRY_COUNT,
            _confirm_instance_deleted,
            (fake_instance, INSTANCE_DELETION_RETRY_COUNT))

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.shelve_vm.django_rq')
    def test_confirm_instance_deleted(self, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        now = datetime.now(utc)
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(code=42)  # the code is ignored

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99', status=VM_WAITING)

        self.assertEqual(WF_SUCCESS,
                         _confirm_instance_deleted(fake_instance, 0))

        mock_rq.get_scheduler.assert_not_called()

        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.deleted)
        volume = Volume.objects.get(pk=instance.boot_volume.pk)
        self.assertIsNotNone(volume.shelved_at)
        self.assertIsNotNone(volume.expiration)
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_SHELVED, vm_status.status)
        self.assertEqual(100, vm_status.status_progress)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.shelve_vm.django_rq')
    def test_confirm_instance_deleted_2(self, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        now = datetime.now(utc)
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99', status=VM_WAITING)
        fake_nectar.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id)

        self.assertEqual(WF_CONTINUE,
                         _confirm_instance_deleted(fake_instance, 3))

        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
            _confirm_instance_deleted, fake_instance, 2)

        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNone(instance.deleted)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.shelve_vm.django_rq')
    def test_confirm_instance_deleted_3(self, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        now = datetime.now(utc)
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99', status=VM_WAITING)
        fake_nectar.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id)

        self.assertEqual(WF_RETRY,
                         _confirm_instance_deleted(fake_instance, 0))

        mock_rq.get_scheduler.assert_not_called()

        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNone(instance.deleted)

    @patch('vm_manager.vm_functions.shelve_vm.shelve_vm_worker')
    def test_shelve_expired_vm(self, mock_shelve):
        now = datetime.now(utc)
        mock_shelve.return_value = WF_SUCCESS

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_OKAY, expires=(now - timedelta(days=2)))

        self.assertEqual(WF_SUCCESS,
                         shelve_expired_vm(fake_instance, self.FEATURE))
        mock_shelve.assert_called_once_with(fake_instance)

    @patch('vm_manager.vm_functions.shelve_vm.shelve_vm_worker')
    def test_shelve_expired_vm_2(self, mock_shelve):
        now = datetime.now(utc)

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_ERROR, expires=(now - timedelta(days=1)))

        self.assertEqual(WF_RETRY,
                         shelve_expired_vm(fake_instance, self.FEATURE))
        mock_shelve.assert_not_called()
