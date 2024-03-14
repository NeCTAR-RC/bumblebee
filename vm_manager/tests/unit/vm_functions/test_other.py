from datetime import timedelta
from unittest.mock import Mock, patch, call

import novaclient

from django.conf import settings

from vm_manager.tests.fakes import FakeServer, FakeNectar
from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase

from vm_manager.constants import ACTIVE, SHUTDOWN, RESCUE, REBOOT, \
    REBOOT_SOFT, REBOOT_HARD, VM_OKAY, VM_ERROR
from vm_manager.models import VMStatus, Volume, Instance
from vm_manager.vm_functions.other_vm_functions import reboot_vm_worker, \
    _check_power_state
from vm_manager.utils.utils import get_nectar


class RebootVMTests(VMFunctionTestBase):

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.other_vm_functions.django_rq')
    @patch('vm_manager.vm_functions.other_vm_functions.logger')
    def test_reboot_vm_worker(self, mock_logger, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_vol, fake_instance, fake_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99')

        mock_server = Mock()
        mock_server.status = ACTIVE
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.return_value = mock_server

        reboot_vm_worker(self.user, fake_instance.id,
                         REBOOT_SOFT, VM_OKAY, self.UBUNTU.feature)

        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)
        mock_server.reboot.assert_called_once_with(REBOOT_SOFT)
        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=settings.REBOOT_CONFIRM_WAIT),
            _check_power_state, settings.REBOOT_CONFIRM_RETRIES,
            fake_instance, VM_OKAY, self.UBUNTU.feature)

        mock_logger.info.assert_called_once_with(
            f"Performing {REBOOT_SOFT} reboot on {fake_instance}")

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(33, updated_status.status_progress)
        self.assertIsNotNone(updated_status.status_message)
        updated_volume = Volume.objects.get(pk=fake_vol.pk)
        self.assertIsNotNone(updated_volume.rebooted_at)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.other_vm_functions.django_rq')
    @patch('vm_manager.vm_functions.other_vm_functions.logger')
    def test_reboot_vm_worker_shutdown(self, mock_logger, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_vol, fake_instance, fake_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99')

        mock_server = Mock()
        mock_server.status = SHUTDOWN
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.return_value = mock_server

        reboot_vm_worker(self.user, fake_instance.id,
                         REBOOT_SOFT, VM_OKAY, self.UBUNTU.feature)

        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)
        mock_server.reboot.assert_called_once_with(REBOOT_HARD)
        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=settings.REBOOT_CONFIRM_WAIT),
            _check_power_state, settings.REBOOT_CONFIRM_RETRIES,
            fake_instance, VM_OKAY, self.UBUNTU.feature)

        mock_logger.info.assert_has_calls([
            call(f"Forcing {REBOOT_HARD} reboot because Nova instance "
                 f"was in state {SHUTDOWN}"),
            call(f"Performing {REBOOT_HARD} reboot on {fake_instance}"),
        ])

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(33, updated_status.status_progress)
        self.assertIsNotNone(updated_status.status_message)
        updated_volume = Volume.objects.get(pk=fake_vol.pk)
        self.assertIsNotNone(updated_volume.rebooted_at)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.other_vm_functions.django_rq')
    @patch('vm_manager.vm_functions.other_vm_functions.logger')
    def test_reboot_vm_worker_wrong_state(self, mock_logger, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_vol, fake_instance, fake_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99')

        mock_server = Mock()
        mock_server.status = RESCUE
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.return_value = mock_server

        reboot_vm_worker(self.user, fake_instance.id,
                         REBOOT_SOFT, VM_OKAY, self.UBUNTU.feature)

        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)
        mock_server.reboot.assert_not_called()
        mock_rq.get_scheduler.assert_not_called()
        mock_logger.info.assert_not_called()
        mock_logger.error.assert_called_once_with(
            f"Nova instance for {fake_instance} in unexpected state {RESCUE}."
            "  Needs manual cleanup.")

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(0, updated_status.status_progress)
        self.assertIsNone(updated_status.status_message)
        updated_volume = Volume.objects.get(pk=fake_vol.pk)
        self.assertIsNone(updated_volume.rebooted_at)
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertEqual(f"Nova instance state is {RESCUE}",
                         instance.error_message)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.other_vm_functions.django_rq')
    @patch('vm_manager.vm_functions.other_vm_functions.logger')
    def test_reboot_vm_worker_missing(self, mock_logger, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_vol, fake_instance, fake_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99')

        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(code=42)  # the code is ignored

        reboot_vm_worker(self.user, fake_instance.id,
                         REBOOT_SOFT, VM_OKAY, self.UBUNTU.feature)

        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)
        mock_rq.get_scheduler.assert_not_called()
        mock_logger.info.assert_not_called()
        mock_logger.error.assert_called_once_with(
            f"Nova instance is missing for {fake_instance}")

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(0, updated_status.status_progress)
        self.assertIsNone(updated_status.status_message)
        updated_volume = Volume.objects.get(pk=fake_vol.pk)
        self.assertIsNone(updated_volume.rebooted_at)
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertEqual("Nova instance is missing", instance.error_message)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.other_vm_functions.django_rq')
    @patch('vm_manager.vm_functions.other_vm_functions.logger')
    def test_check_power_state(self, mock_logger, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        _, fake_instance, fake_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99')

        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.return_value = FakeServer(status=ACTIVE)

        _check_power_state(1, fake_instance,
                           VM_OKAY, self.UBUNTU.feature)

        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)
        mock_rq.get_scheduler.assert_not_called()
        mock_logger.info.assert_called_once_with(
            f"Instance {fake_instance.id} is {ACTIVE}")
        mock_logger.error.assert_not_called()

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(66, updated_status.status_progress)
        self.assertIsNotNone(updated_status.status_message)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.other_vm_functions.django_rq')
    @patch('vm_manager.vm_functions.other_vm_functions.logger')
    def test_check_power_state_2(self, mock_logger, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        _, fake_instance, fake_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99')

        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.return_value = FakeServer(status=REBOOT)

        _check_power_state(1, fake_instance,
                           VM_OKAY, self.UBUNTU.feature)

        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)

        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=settings.REBOOT_CONFIRM_WAIT),
            _check_power_state, 0, fake_instance, VM_OKAY, self.UBUNTU.feature)

        mock_logger.info.assert_not_called()
        mock_logger.error.assert_not_called()

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(0, updated_status.status_progress)
        self.assertIsNone(updated_status.status_message)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.other_vm_functions.django_rq')
    @patch('vm_manager.vm_functions.other_vm_functions.logger')
    def test_check_power_state_3(self, mock_logger, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        _, fake_instance, fake_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99')

        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.return_value = FakeServer(status=REBOOT)

        _check_power_state(0, fake_instance,
                           VM_OKAY, self.UBUNTU.feature)

        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)

        mock_rq.get_scheduler.assert_not_called()
        mock_scheduler.enqueue_in.assert_not_called()

        mock_logger.info.assert_not_called()
        mock_logger.error.assert_called_once_with(
            f"Instance {fake_instance.id} has not gone {ACTIVE} after reboot")

        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(0, updated_status.status_progress)
        self.assertIsNone(updated_status.status_message)
        self.assertEqual(VM_ERROR, updated_status.status)
