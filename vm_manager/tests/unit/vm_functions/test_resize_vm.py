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

from vm_manager.constants import ACTIVE, SHUTDOWN, RESIZE, VERIFY_RESIZE, \
    VM_ERROR, VM_RESIZING, VM_MISSING, VM_OKAY, VM_SHELVED, NO_VM, \
    VM_WAITING, VM_SUPERSIZED, RESIZE_CONFIRM_WAIT_SECONDS, \
    REBOOT_COMPLETE_SECONDS, FORCED_DOWNSIZE_WAIT_SECONDS
from vm_manager.models import VMStatus, Volume, Instance, Resize
from vm_manager.vm_functions.resize_vm import supersize_vm_worker, \
    downsize_vm_worker, extend_boost, _resize_vm, _wait_to_confirm_resize, \
    downsize_expired_supersized_vms
from vm_manager.utils.utils import get_nectar, after_time
from vm_manager.utils.expiry import BoostExpiryPolicy


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
            fake_instance, self.UBUNTU.big_flavor.id, VM_SUPERSIZED,
            self.FEATURE)

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
        exp_date = BoostExpiryPolicy().initial_expiry(now=resize.requested)
        # Getting the resize expiry date to exactly match in this context
        # is too tricky ... and unnecessary.
        self.assertTrue(abs((exp_date - resize.expires).seconds) < 2)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm._resize_vm')
    @patch('vm_manager.vm_functions.resize_vm.logger')
    def test_downsize_vm_worker_no_resize_record(
            self, mock_logger, mock_resize):
        fake_nectar = get_nectar()

        _, fake_instance = self.build_fake_vol_instance(ip_address='10.0.0.99')
        mock_resize.return_value = "x"

        self.assertEqual("x", downsize_vm_worker(fake_instance, self.UBUNTU))
        mock_resize.assert_called_once_with(
            fake_instance, self.UBUNTU.default_flavor.id,
            VM_OKAY, self.FEATURE)

        mock_logger.info.assert_called_once_with(
            f"About to downsize {self.UBUNTU.id} vm "
            f"for user {self.user.username}"
        )
        mock_logger.error_assert_called_once_with(
            f"Missing resize record for instance {fake_instance}")

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm._resize_vm')
    @patch('vm_manager.vm_functions.resize_vm.logger')
    def test_downsize_vm_worker(self, mock_logger, mock_resize):
        fake_nectar = get_nectar()

        _, fake_instance = self.build_fake_vol_instance(ip_address='10.0.0.99')
        mock_resize.return_value = "x"
        resize = ResizeFactory.create(instance=fake_instance)

        self.assertEqual("x", downsize_vm_worker(fake_instance, self.UBUNTU))
        mock_resize.assert_called_once_with(
            fake_instance, self.UBUNTU.default_flavor.id,
            VM_OKAY, self.FEATURE)

        mock_logger.info.assert_called_once_with(
            f"About to downsize {self.UBUNTU.id} vm "
            f"for user {self.user.username}"
        )
        mock_logger.error_assert_not_called()

        resize = Resize.objects.get(pk=resize.pk)
        self.assertIsNotNone(resize.reverted)

    @patch('vm_manager.models.logger')
    @patch('vm_manager.vm_functions.resize_vm.BoostExpiryPolicy')
    def test_extend(self, mock_policy_class, mock_logger):
        mock_policy = Mock()
        mock_policy_class.return_value = mock_policy

        id = uuid.uuid4()
        with self.assertRaises(Http404):
            extend_boost(self.user, id, self.FEATURE)

        mock_logger.error.assert_called_with(
            f"Trying to get a vm that doesn't exist with vm_id: {id}, "
            f"called by {self.user}")

        _, fake_instance = self.build_fake_vol_instance()
        self.assertEqual(
            f"No Resize is current for instance {fake_instance}",
            extend_boost(self.user, fake_instance.id, self.FEATURE))

        now = datetime.now(timezone.utc)
        new_expiry = now + timedelta(days=settings.BOOST_EXPIRY)
        mock_policy.new_expiry.return_value = new_expiry

        resize = ResizeFactory.create(instance=fake_instance, reverted=now)
        self.assertEqual(
            f"No Resize is current for instance {fake_instance}",
            extend_boost(self.user, fake_instance.id, self.FEATURE))

        resize = ResizeFactory.create(instance=fake_instance)
        res = extend_boost(self.user, fake_instance.id, self.FEATURE)
        self.assertTrue(res.startswith(
            f"Resize (Current) of Instance ({fake_instance.id})"))

        updated_resize = Resize.objects.get(pk=resize.pk)
        self.assertEqual(new_expiry, updated_resize.expires)
        mock_policy.new_expiry.assert_called_once_with(resize)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm.django_rq')
    @patch('vm_manager.vm_functions.resize_vm.after_time')
    def test_resize_vm(self, mock_after_time, mock_rq):
        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_RESIZING, status_progress=0)
        default_flavor_id = self.UBUNTU.default_flavor.id
        big_flavor_id = self.UBUNTU.big_flavor.id
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler

        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.return_value = FakeServer(
            flavor={'id': str(default_flavor_id)})
        fake_nectar.nova.servers.resize.return_value = "whatever"
        self.assertEqual(
            f"Instance {fake_instance.id} already has flavor "
            f"{default_flavor_id}. Skipping the resize.",
            _resize_vm(fake_instance, default_flavor_id,
                       VM_OKAY, self.FEATURE))
        fake_nectar.nova.servers.get.assert_called_with(fake_instance.id)
        fake_nectar.nova.servers.get.reset_mock()

        after = (datetime.now(timezone.utc)
                 + timedelta(RESIZE_CONFIRM_WAIT_SECONDS))
        mock_after_time.return_value = after

        self.assertEqual(
            "whatever",
            _resize_vm(fake_instance, big_flavor_id,
                       VM_SUPERSIZED, self.FEATURE))

        fake_nectar.nova.servers.get.assert_called_with(fake_instance.id)
        fake_nectar.nova.servers.resize.assert_called_with(
            fake_instance.id, big_flavor_id)

        mock_rq.get_scheduler.assert_called_once_with("default")
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=5), _wait_to_confirm_resize,
            fake_instance, big_flavor_id, VM_SUPERSIZED, after,
            self.FEATURE)
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(33, vm_status.status_progress)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm.logger')
    @patch('vm_manager.vm_functions.resize_vm.django_rq')
    def test_wait_to_confirm_resize(self, mock_rq, mock_logger):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.return_value = FakeServer(
            status=VERIFY_RESIZE)
        fake_nectar.nova.servers.confirm_resize.reset_mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_RESIZING, status_progress=50)

        self.assertEqual(
            f"Status of [{self.FEATURE.name}][{self.UBUNTU.id}]"
            f"[{self.user}] is {VM_WAITING}",
            _wait_to_confirm_resize(
                fake_instance, self.UBUNTU.default_flavor.id,
                VM_OKAY, after_time(10), self.FEATURE))
        mock_logger.info.assert_called_once_with(
            f"Confirming resize of {fake_instance}")
        fake_nectar.nova.servers.confirm_resize.assert_called_once_with(
            fake_instance.id)
        mock_scheduler.enqueue_in.assert_not_called()
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(66, vm_status.status_progress)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm.logger')
    @patch('vm_manager.vm_functions.resize_vm.django_rq')
    def test_wait_to_confirm_resize_2(self, mock_rq, mock_logger):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.return_value = FakeServer(
            status=RESIZE)
        fake_nectar.nova.servers.confirm_resize.reset_mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_RESIZING, status_progress=50)

        deadline = after_time(10)
        self.assertEqual(
            f"Status of [{self.FEATURE.name}][{self.UBUNTU.id}]"
            f"[{self.user}] is {VM_RESIZING}",
            _wait_to_confirm_resize(
                fake_instance, self.UBUNTU.default_flavor.id,
                VM_OKAY, deadline, self.FEATURE))
        mock_logger.info.assert_called_once_with(
            f"Waiting for resize of {fake_instance}")
        mock_logger.error.assert_not_called()
        fake_nectar.nova.servers.confirm_resize.assert_not_called()
        mock_rq.get_scheduler.assert_called_once_with("default")
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=5), _wait_to_confirm_resize,
            fake_instance, self.UBUNTU.default_flavor.id,
            VM_OKAY, deadline, self.FEATURE)
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(50, vm_status.status_progress)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm.logger')
    @patch('vm_manager.vm_functions.resize_vm.django_rq')
    def test_wait_to_confirm_resize_3(self, mock_rq, mock_logger):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.return_value = FakeServer(
            status=RESIZE)
        fake_nectar.nova.servers.confirm_resize.reset_mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_RESIZING, status_progress=50)

        deadline = after_time(-10)
        res = _wait_to_confirm_resize(
            fake_instance, self.UBUNTU.default_flavor.id,
            VM_OKAY, deadline, self.FEATURE)
        error = (f"Instance ({fake_instance}) resize failed instance in "
                 f"state: {RESIZE}")
        self.assertEqual(error, res)
        mock_logger.info.assert_called_once_with(
            f"Waiting for resize of {fake_instance}")
        mock_logger.error.assert_has_calls([
            call("Resize has taken too long"),
            call(error)])
        fake_nectar.nova.servers.confirm_resize.assert_not_called()
        mock_rq.get_scheduler.assert_not_called()
        mock_scheduler.enqueue_in.assert_not_called()
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_ERROR, vm_status.status)
        self.assertEqual(error, vm_status.instance.error_message)
        self.assertEqual(error, vm_status.instance.boot_volume.error_message)
        self.assertEqual(50, vm_status.status_progress)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm.logger')
    @patch('vm_manager.vm_functions.resize_vm.django_rq')
    def test_wait_to_confirm_resize_4(self, mock_rq, mock_logger):
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.side_effect = [
            # This is messy.  We want a specific 'nova.get' call to fail.
            # It also illustrates a problem with the code under test.
            # It is actually making multiple calls to 'nova.get' under
            # the hood to get the status (3 times) then the flavor.
            FakeServer(status=ACTIVE), FakeServer(status=ACTIVE),
            FakeServer(status=ACTIVE), Exception("bad")
        ]
        fake_nectar.nova.servers.confirm_resize.reset_mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_RESIZING, status_progress=50)

        deadline = after_time(10)
        self.assertIsNone(_wait_to_confirm_resize(
            fake_instance, self.UBUNTU.default_flavor.id,
            VM_OKAY, deadline, self.FEATURE))
        error = (f"Something went wrong with the instance get call "
                 f"for {fake_instance}: it raised bad")
        mock_logger.error.assert_called_once_with(error)
        fake_nectar.nova.servers.confirm_resize.assert_not_called()
        mock_rq.get_scheduler.assert_not_called()
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(50, vm_status.status_progress)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm.logger')
    @patch('vm_manager.vm_functions.resize_vm.django_rq')
    def test_wait_to_confirm_resize_5(self, mock_rq, mock_logger):
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.side_effect = None
        fake_nectar.nova.servers.get.return_value = FakeServer(
            status=ACTIVE, flavor={'id': str(self.UBUNTU.big_flavor.id)})
        fake_nectar.nova.servers.confirm_resize.reset_mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_RESIZING, status_progress=50)

        deadline = after_time(10)
        res = _wait_to_confirm_resize(
            fake_instance, self.UBUNTU.default_flavor.id,
            VM_OKAY, deadline, self.FEATURE)
        error = (f"Instance ({fake_instance}) resize failed as "
                 f"instance hasn't changed flavor: "
                 f"Actual Flavor: {self.UBUNTU.big_flavor.id}, "
                 f"Expected Flavor: {self.UBUNTU.default_flavor.id}")
        self.assertEqual(error, res)
        mock_logger.info.assert_not_called()
        mock_logger.error.assert_called_once_with(error)
        fake_nectar.nova.servers.confirm_resize.assert_not_called()
        mock_rq.get_scheduler.assert_not_called()
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_ERROR, vm_status.status)
        self.assertEqual(error, vm_status.instance.error_message)
        self.assertEqual(error, vm_status.instance.boot_volume.error_message)
        self.assertEqual(50, vm_status.status_progress)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm.logger')
    @patch('vm_manager.vm_functions.resize_vm.django_rq')
    def test_wait_to_confirm_resize_6(self, mock_rq, mock_logger):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.side_effect = None
        fake_nectar.nova.servers.get.return_value = FakeServer(
            status=ACTIVE, flavor={'id': str(self.UBUNTU.big_flavor.id)})
        fake_nectar.nova.servers.confirm_resize.reset_mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_RESIZING, status_progress=50)

        deadline = after_time(10)
        res = _wait_to_confirm_resize(
            fake_instance, self.UBUNTU.big_flavor.id,
            VM_SUPERSIZED, deadline, self.FEATURE)
        msg = f"Resize of {fake_instance} was confirmed automatically"
        self.assertEqual(msg, res)
        mock_logger.info.assert_called_once_with(msg)
        mock_logger.error.assert_not_called()
        fake_nectar.nova.servers.confirm_resize.assert_not_called()
        mock_scheduler.enqueue_in.assert_not_called()

        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertEqual(66, vm_status.status_progress)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm.logger')
    @patch('vm_manager.vm_functions.resize_vm.django_rq')
    def test_wait_to_confirm_resize_7(self, mock_rq, mock_logger):
        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.side_effect = None
        fake_nectar.nova.servers.get.return_value = FakeServer(status=SHUTDOWN)
        fake_nectar.nova.servers.confirm_resize.reset_mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_RESIZING, status_progress=50)

        deadline = after_time(10)
        res = _wait_to_confirm_resize(
            fake_instance, self.UBUNTU.big_flavor.id,
            VM_SUPERSIZED, deadline, self.FEATURE)
        error = (
            f"Instance ({fake_instance}) resize failed instance in "
            f"state: {SHUTDOWN}")
        self.assertEqual(error, res)
        mock_logger.info.assert_not_called()
        mock_logger.error.assert_called_once_with(error)
        fake_nectar.nova.servers.confirm_resize.assert_not_called()
        mock_rq.get_scheduler.assert_not_called()
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_ERROR, vm_status.status)
        self.assertEqual(error, vm_status.instance.error_message)
        self.assertEqual(error, vm_status.instance.boot_volume.error_message)
        self.assertEqual(50, vm_status.status_progress)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm.logger')
    @patch('vm_manager.vm_functions.resize_vm._resize_vm')
    def test_downsize_expired_supersized_vms(self, mock_resize, mock_logger):
        now = datetime.now(timezone.utc)
        fake_nectar = get_nectar()
        self.assertEqual(0, downsize_expired_supersized_vms(self.FEATURE))

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_SUPERSIZED)

        resize = ResizeFactory.create(
            instance=fake_instance,
            expires=(now - timedelta(days=1)))

        self.assertEqual(1, downsize_expired_supersized_vms(self.FEATURE))
        mock_resize.assert_called_once_with(
            fake_instance, self.UBUNTU.default_flavor.id,
            VM_OKAY, self.FEATURE)
        resize = Resize.objects.get(pk=resize.pk)
        self.assertIsNotNone(resize.reverted)
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_RESIZING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
        self.assertTrue(vm_status.wait_time >= now + timedelta(
            seconds=FORCED_DOWNSIZE_WAIT_SECONDS))

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.resize_vm.logger')
    @patch('vm_manager.vm_functions.resize_vm._resize_vm')
    def test_downsize_expired_supersized_vms_2(self, mock_resize, mock_logger):
        now = datetime.now(timezone.utc)
        fake_nectar = get_nectar()
        self.assertEqual(0, downsize_expired_supersized_vms(self.FEATURE))

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_ERROR)

        resize = ResizeFactory.create(
            instance=fake_instance,
            expires=(now - timedelta(days=1)))

        self.assertEqual(0, downsize_expired_supersized_vms(self.FEATURE))
        mock_resize.assert_not_called()
