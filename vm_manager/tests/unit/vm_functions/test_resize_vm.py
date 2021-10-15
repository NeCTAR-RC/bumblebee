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

from vm_manager.constants import ACTIVE, SHUTDOWN, \
    VM_MISSING, VM_OKAY, VM_SHELVED, NO_VM, DOWNSIZE_PERIOD, \
    RESIZE_CONFIRM_WAIT_SECONDS
from vm_manager.models import VMStatus, Volume, Instance, Resize
from vm_manager.vm_functions.resize_vm import supersize_vm_worker, \
    downsize_vm_worker, calculate_supersize_expiration_date, \
    extend, _resize_vm, _wait_to_confirm_resize
from vm_manager.utils.utils import get_nectar


class ResizeVMTests(VMFunctionTestBase):

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm._resize_vm')
    @patch('vm_manager.vm_functions.resize_vm.logger')
    def test_supersize_vm_worker(self, mock_logger, mock_resize):
        fake_nectar = get_nectar()

        _, fake_instance = self.build_fake_vol_instance(ip_address='10.0.0.99')
        mock_resize.return_value = "x"

        self.assertEqual(0, Resize.objects.all().count())

        self.assertEqual("x", supersize_vm_worker(fake_instance, self.UBUNTU))
        mock_resize.assert_called_once_with(
            fake_instance, self.UBUNTU.big_flavor.id, self.FEATURE)

        mock_logger.info.assert_called_once_with(
            f"About to supersize {self.UBUNTU.id} vm "
            f"for user {self.user.username}"
        )
        self.assertEqual(
            1, Resize.objects.filter(instance=fake_instance).count())
        resize = Resize.objects.filter(instance=fake_instance).first()
        self.assertEqual(fake_instance, resize.instance)
        self.assertIsNotNone(resize.requested)
        self.assertIsNone(resize.reverted)
        exp_date = calculate_supersize_expiration_date(resize.requested.date())
        self.assertEqual(exp_date, resize.expires)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm._resize_vm')
    @patch('vm_manager.vm_functions.resize_vm.logger')
    def test_downsize_vm_worker_no_resize(self, mock_logger, mock_resize):
        fake_nectar = get_nectar()

        _, fake_instance = self.build_fake_vol_instance(ip_address='10.0.0.99')
        mock_resize.return_value = "x"

        self.assertEqual("x", downsize_vm_worker(fake_instance, self.UBUNTU))
        mock_resize.assert_called_once_with(
            fake_instance, self.UBUNTU.default_flavor.id, self.FEATURE)

        mock_logger.info.assert_called_once_with(
            f"About to downsize {self.UBUNTU.id} vm "
            f"for user {self.user.username}"
        )
        mock_logger.error_assert_called_once_with(
            f"Missing resize record for instance {fake_instance}")

    @patch('vm_manager.vm_functions.resize_vm._resize_vm')
    @patch('vm_manager.vm_functions.resize_vm.logger')
    def test_downsize_vm_worker(self, mock_logger, mock_resize):
        fake_nectar = get_nectar()

        _, fake_instance = self.build_fake_vol_instance(ip_address='10.0.0.99')
        mock_resize.return_value = "x"
        resize = ResizeFactory.create(instance=fake_instance)

        self.assertEqual("x", downsize_vm_worker(fake_instance, self.UBUNTU))
        mock_resize.assert_called_once_with(
            fake_instance, self.UBUNTU.default_flavor.id, self.FEATURE)

        mock_logger.info.assert_called_once_with(
            f"About to downsize {self.UBUNTU.id} vm "
            f"for user {self.user.username}"
        )
        mock_logger.error_assert_not_called()

        resize = Resize.objects.get(pk=resize.pk)
        self.assertIsNotNone(resize.reverted)

    @patch('vm_manager.models.logger')
    def test_extend(self, mock_logger):
        id = uuid.uuid4()
        with self.assertRaises(Http404):
            extend(self.user, id, self.FEATURE)

        mock_logger.error.assert_called_with(
            f"Trying to get a vm that doesn't exist with vm_id: {id}, "
            f"called by {self.user}")

        _, fake_instance = self.build_fake_vol_instance()
        self.assertEqual(f"No Resize is current for instance {fake_instance}",
                         extend(self.user, fake_instance.id, self.FEATURE))

        now = datetime.now(timezone.utc)
        resize = ResizeFactory.create(
            instance=fake_instance, reverted=now)
        self.assertEqual(f"No Resize is current for instance {fake_instance}",
                         extend(self.user, fake_instance.id, self.FEATURE))

        resize = ResizeFactory.create(
            instance=fake_instance, expires=(now + timedelta(days=8)))
        new_exp_date = (now + timedelta(days=8)).date()
        self.assertEqual(
            f"Resize (id {resize.id}) date too far in future: {new_exp_date}",
            extend(self.user, fake_instance.id, self.FEATURE))

        resize = ResizeFactory.create(
            instance=fake_instance, expires=now)
        self.assertEqual(
            f"Resize (Current) of Instance ({fake_instance.id}) "
            f"requested on {now.date()}",
            extend(self.user, fake_instance.id, self.FEATURE))
        resize = Resize.objects.get(pk=resize.pk)
        self.assertEqual(calculate_supersize_expiration_date(now.date()),
                         resize.expires)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm.django_rq')
    @patch('vm_manager.vm_functions.resize_vm.after_time')
    def test_resize_vm(self, mock_after_time, mock_rq):
        _, fake_instance = self.build_fake_vol_instance()
        default_flavor_id = self.UBUNTU.default_flavor.id
        big_flavor_id = self.UBUNTU.big_flavor.id
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler

        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.return_value = FakeServer(
            flavor=FakeFlavor(id=default_flavor_id))
        fake_nectar.nova.servers.resize.return_value = "whatever"
        self.assertEqual(
            f"Instance {fake_instance.id} already has flavor "
            f"{default_flavor_id}. Skipping the resize.",
            _resize_vm(fake_instance, default_flavor_id, self.FEATURE))
        fake_nectar.nova.servers.get.assert_called_with(fake_instance.id)
        fake_nectar.nova.servers.get.reset_mock()

        after = (datetime.now(timezone.utc)
                 + timedelta(RESIZE_CONFIRM_WAIT_SECONDS))
        mock_after_time.return_value = after

        self.assertEqual(
            "whatever",
            _resize_vm(fake_instance, big_flavor_id, self.FEATURE))

        fake_nectar.nova.servers.get.assert_called_with(fake_instance.id)
        fake_nectar.nova.servers.resize.assert_called_with(
            fake_instance.id, big_flavor_id)

        mock_rq.get_scheduler.assert_called_once_with("default")
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=5),
            _wait_to_confirm_resize,
            fake_instance, big_flavor_id,
            after,
            self.FEATURE)
