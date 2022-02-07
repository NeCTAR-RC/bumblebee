import copy
from datetime import datetime, timedelta, timezone
import uuid

import novaclient

from unittest.mock import Mock, patch, call

from django.conf import settings
from django.test import TestCase
from django.http import Http404

from researcher_desktop.utils.utils import get_desktop_type, desktops_feature
from vm_manager.tests.factories import ResizeFactory
from vm_manager.tests.common import UUID_1, UUID_2, UUID_3, UUID_4
from vm_manager.tests.fakes import Fake, FakeServer, FakeFlavor, FakeNectar
from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase

from vm_manager.constants import VM_OKAY, VM_WAITING, VM_ERROR, \
    FORCED_SHELVE_WAIT_SECONDS
from vm_manager.models import VMStatus
from vm_manager.vm_functions.shelve_vm import shelve_vm_worker, \
    shelve_expired_vms
from vm_manager.utils.utils import get_nectar, after_time


class ShelveVMTests(VMFunctionTestBase):

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.shelve_vm.shelve_vm_worker')
    def test_shelve_expired_vms(self, mock_shelve):
        now = datetime.now(timezone.utc)
        fake_nectar = get_nectar()
        self.assertEqual(0, shelve_expired_vms(self.FEATURE))

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_OKAY, expires=(now - timedelta(days=2)))

        self.assertEqual(1, shelve_expired_vms(self.FEATURE))
        mock_shelve.assert_called_once_with(
            fake_instance, self.FEATURE)
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
        self.assertTrue(vm_status.wait_time >= now + timedelta(
            seconds=FORCED_SHELVE_WAIT_SECONDS))

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.shelve_vm.shelve_vm_worker')
    def test_downsize_expired_supersized_vms_2(self, mock_shelve):
        now = datetime.now(timezone.utc)
        fake_nectar = get_nectar()
        self.assertEqual(0, shelve_expired_vms(self.FEATURE))

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_ERROR, expires=(now - timedelta(days=1)))

        self.assertEqual(0, shelve_expired_vms(self.FEATURE))
        mock_shelve.assert_not_called()
