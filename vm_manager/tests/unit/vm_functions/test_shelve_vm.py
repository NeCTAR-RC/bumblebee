from datetime import datetime, timedelta
from unittest.mock import patch

from django.utils.timezone import utc

from vm_manager.constants import VM_OKAY, VM_WAITING, VM_ERROR, \
    FORCED_SHELVE_WAIT_SECONDS
from vm_manager.models import VMStatus
from vm_manager.tests.fakes import FakeNectar
from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase
from vm_manager.utils.utils import get_nectar
from vm_manager.vm_functions.shelve_vm import shelve_expired_vm


class ShelveVMTests(VMFunctionTestBase):

    # TODO - tests for shelve_vm_worker

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.shelve_vm.shelve_vm_worker')
    def test_shelve_expired_vm(self, mock_shelve):
        now = datetime.now(utc)
        fake_nectar = get_nectar()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_OKAY, expires=(now - timedelta(days=2)))

        self.assertEqual(1, shelve_expired_vm(fake_instance, self.FEATURE))
        mock_shelve.assert_called_once_with(
            fake_instance, self.FEATURE)
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
        self.assertTrue(vm_status.wait_time >= now + timedelta(
            seconds=FORCED_SHELVE_WAIT_SECONDS))

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.shelve_vm.shelve_vm_worker')
    def test_shelve_expired_vm_2(self, mock_shelve):
        now = datetime.now(utc)
        fake_nectar = get_nectar()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_ERROR, expires=(now - timedelta(days=1)))

        self.assertEqual(0, shelve_expired_vm(fake_instance, self.FEATURE))
        mock_shelve.assert_not_called()
