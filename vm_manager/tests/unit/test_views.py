from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, call
import uuid

from django.conf import settings
from django.http import Http404
from django.test import TestCase

from researcher_workspace.tests.factories import UserFactory
from researcher_desktop.tests.factories import DesktopTypeFactory, \
    AvailabilityZoneFactory
from researcher_desktop.utils.utils import get_desktop_type, desktops_feature
from vm_manager.tests.factories import InstanceFactory, VolumeFactory, \
    ResizeFactory, VMStatusFactory
from vm_manager.tests.fakes import Fake, FakeNectar

from vm_manager.constants import ACTIVE, SHUTDOWN, BUILD, REBUILD, \
    REBOOT, RESCUE, REBOOT_SOFT, VM_OKAY, VM_DELETED, VM_WAITING, \
    VM_CREATING, VM_RESIZING, NO_VM, VM_SHELVED, VM_MISSING, VM_ERROR, \
    VM_SHUTDOWN, VM_SUPERSIZED, ALL_VM_STATES, \
    CLOUD_INIT_STARTED, CLOUD_INIT_FINISHED, SCRIPT_OKAY, \
    EXTEND_BUTTON, EXTEND_BOOST_BUTTON, BOOST_BUTTON

from vm_manager.models import VMStatus, Instance, Volume, Resize, Expiration, \
    EXP_INITIAL, EXP_FIRST_WARNING, EXP_EXPIRING, EXP_EXPIRY_COMPLETED, \
    EXP_EXPIRY_FAILED_RETRYABLE
from vm_manager.utils.utils import get_nectar, after_time
from vm_manager.views import launch_vm_worker, delete_vm_worker, \
    shelve_vm_worker, unshelve_vm_worker, reboot_vm_worker, \
    supersize_vm_worker, downsize_vm_worker

from vm_manager.views import launch_vm, delete_vm, shelve_vm, unshelve_vm, \
    reboot_vm, supersize_vm, downsize_vm, get_vm_state, render_vm, notify_vm, \
    phone_home, rd_report_for_user, delete_shelved_vm

utc = timezone.utc


class VMManagerViewTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()
        self.FEATURE = desktops_feature()
        self.UBUNTU = get_desktop_type('ubuntu')
        self.zone = AvailabilityZoneFactory.create(name="a_zone",
                                                   zone_weight=1)

    def build_existing_vm(self, status, expires=None, volume_expires=None,
                          stage=EXP_INITIAL):
        self.volume = VolumeFactory.create(
            id=uuid.uuid4(), user=self.user,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.FEATURE,
            zone=self.zone.name)
        self.instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=self.volume,
            ip_address='10.0.0.1')
        if expires:
            self.instance.set_expires(expires, stage=stage)
        if volume_expires:
            self.volume.set_expires(volume_expires, stage=stage)
        if status:
            self.vm_status = VMStatusFactory.create(
                instance=self.instance,
                user=self.user,
                operating_system=self.UBUNTU.id,
                requesting_feature=self.FEATURE,
                status=status)
        else:
            self.vm_status = None

    @patch('vm_manager.views.django_rq')
    def test_launch_vm_exists(self, mock_rq):
        self.build_existing_vm(VM_OKAY)
        self.assertEqual(
            f"User {self.user} already has 1 live desktops",
            launch_vm(self.user, self.UBUNTU, self.zone))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_launch_vm_not_properly_deleted(self, mock_rq):
        self.build_existing_vm(VM_DELETED)

        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue

        self.assertEqual(
            f"User {self.user} already has 1 live desktops",
            launch_vm(self.user, self.UBUNTU, self.zone))
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.UBUNTU)

    @patch('vm_manager.views.django_rq')
    def test_launch_vm(self, mock_rq):
        self.build_existing_vm(VM_DELETED)

        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        now = datetime.now(utc)

        self.instance.deleted = now
        self.instance.save()

        self.assertEqual(
            f"Status of {self.UBUNTU} for {self.user} "
            f"is {VM_WAITING}",
            launch_vm(self.user, self.UBUNTU, self.zone))
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.UBUNTU)
        self.assertTrue(vm_status != self.vm_status)
        self.assertEqual(VM_CREATING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
        self.assertEqual(self.UBUNTU.id, vm_status.operating_system)
        self.assertEqual(self.FEATURE, vm_status.requesting_feature)
        self.assertTrue(now <= vm_status.created)
        self.assertTrue(after_time(settings.LAUNCH_WAIT)
                        >= vm_status.wait_time)

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            launch_vm_worker, user=self.user, desktop_type=self.UBUNTU,
            zone=self.zone)

    @patch('vm_manager.views.django_rq')
    def test_delete_vm_inconsistent(self, mock_rq):
        with self.assertRaises(Http404):
            delete_vm(self.user, uuid.uuid4(), self.FEATURE)

        self.build_existing_vm(None)
        self.assertEqual(
            f"VMStatus for user {self.user}, feature {self.FEATURE} "
            "is missing. Cannot delete VM.",
            delete_vm(self.user, self.instance.id, self.FEATURE))

        self.build_existing_vm(NO_VM)
        self.assertEqual(
            f"VMStatus for user {self.user}, feature {self.FEATURE}, "
            f"instance {self.instance.id} is in wrong state ({NO_VM}). "
            "Cannot delete VM.",
            delete_vm(self.user, self.instance.id, self.FEATURE))

        self.build_existing_vm(VM_DELETED)
        self.assertEqual(
            f"VMStatus for user {self.user}, feature {self.FEATURE}, "
            f"instance {self.instance.id} is in wrong state ({VM_DELETED}). "
            "Cannot delete VM.",
            delete_vm(self.user, self.instance.id, self.FEATURE))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_delete_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue

        self.build_existing_vm(VM_OKAY)
        self.assertEqual(
            f"Status of {self.UBUNTU.id} for "
            f"{self.user} is {NO_VM}",
            delete_vm(self.user, self.instance.id, self.FEATURE))

        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertEqual(VM_DELETED, vm_status.status)
        # No progress changes required when deleting
        self.assertIsNotNone(vm_status.instance.marked_for_deletion)
        self.assertIsNotNone(
            vm_status.instance.boot_volume.marked_for_deletion)

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            delete_vm_worker, self.instance)

    @patch('vm_manager.views.django_rq')
    def test_shelve_vm_inconsistent(self, mock_rq):
        with self.assertRaises(Http404):
            shelve_vm(self.user, uuid.uuid4(), self.FEATURE)

        self.build_existing_vm(None)
        self.assertEqual(
            f"VMStatus for user {self.user}, "
            f"feature {self.FEATURE}, instance {self.instance.id} "
            "is missing. Cannot shelve VM.",
            shelve_vm(self.user, self.instance.id, self.FEATURE))

        for status in ALL_VM_STATES - {VM_OKAY, VM_SUPERSIZED}:
            self.build_existing_vm(status)
            self.assertEqual(
                f"VMStatus for user {self.user}, "
                f"feature {self.FEATURE}, instance {self.instance.id} "
                f"is in wrong state ({status}). Cannot shelve VM.",
                shelve_vm(self.user, self.instance.id, self.FEATURE))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_shelve_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_OKAY)

        self.assertEqual(
            f"Status of {self.UBUNTU.id} for {self.user} "
            f"is {VM_WAITING}",
            shelve_vm(self.user, self.instance.id, self.FEATURE))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            shelve_vm_worker, self.instance)
        vm_status = VMStatus.objects.get(pk=self.vm_status.id)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
        self.assertIsNotNone(vm_status.instance.marked_for_deletion)
        self.assertIsNone(vm_status.instance.boot_volume.marked_for_deletion)

    @patch('vm_manager.views.django_rq')
    def test_unshelve_vm_inconsistent(self, mock_rq):
        self.assertEqual(
            f"VMStatus for user {self.user}, "
            f"desktop_type {self.UBUNTU.id} "
            "is missing. Cannot unshelve VM.",
            unshelve_vm(self.user, self.UBUNTU))

        for status in ALL_VM_STATES - {VM_SHELVED}:
            self.build_existing_vm(status)
            now = datetime.now(utc)
            self.instance.deleted = now
            self.instance.save()
            self.assertEqual(
                f"VMStatus for user {self.user}, "
                f"desktop_type {self.UBUNTU.id}, "
                f"instance {self.instance.id} "
                f"is in wrong state ({status}). Cannot unshelve VM.",
                unshelve_vm(self.user, self.UBUNTU))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_unshelve_vm_existing(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_SHELVED)

        self.assertEqual(
            f"User {self.user} already has 1 live desktops",
            unshelve_vm(self.user, self.UBUNTU))
        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_unshelve_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_SHELVED)
        now = datetime.now(utc)
        self.instance.deleted = now
        self.instance.save()

        self.assertEqual(
            f"Status of {self.UBUNTU.id} for {self.user} "
            f"is {VM_CREATING}",
            unshelve_vm(self.user, self.UBUNTU))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            unshelve_vm_worker, user=self.user, desktop_type=self.UBUNTU,
            zone=self.zone)
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.UBUNTU)
        self.assertTrue(vm_status.pk != self.vm_status.pk)
        self.assertEqual(VM_CREATING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
        self.assertIsNone(vm_status.instance)
        self.assertEqual(vm_status.operating_system, self.UBUNTU.id)
        self.assertEqual(vm_status.requesting_feature, self.FEATURE)

    @patch('vm_manager.views.django_rq')
    def test_reboot_vm_inconsistent(self, mock_rq):
        with self.assertRaises(Http404):
            reboot_vm(self.user, uuid.uuid4(), REBOOT_SOFT, self.FEATURE)

        self.build_existing_vm(None)
        with self.assertRaises(VMStatus.DoesNotExist):
            reboot_vm(self.user, self.instance.id, REBOOT_SOFT, self.FEATURE)

        for status in ALL_VM_STATES - {VM_OKAY, VM_SUPERSIZED}:
            self.build_existing_vm(status)
            self.assertEqual(
                f"VMStatus for user {self.user}, feature {self.FEATURE}, "
                f"instance {self.instance.id} is in wrong state ({status}). "
                "Cannot reboot VM.",
                reboot_vm(self.user, self.instance.id,
                          REBOOT_SOFT, self.FEATURE))

        self.build_existing_vm(VM_OKAY)
        with self.assertRaises(Http404):
            reboot_vm(self.user, self.instance.id, "squirrelly", self.FEATURE)

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_reboot_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_OKAY)
        now = datetime.now(utc)

        self.assertEqual(
            f"Status of {self.UBUNTU.id} for "
            f"{self.user} is {VM_WAITING}",
            reboot_vm(self.user, self.instance.id, REBOOT_SOFT, self.FEATURE))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            reboot_vm_worker, self.user, self.instance.id, REBOOT_SOFT,
            VM_OKAY, self.FEATURE)
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.UBUNTU)
        self.assertEqual(vm_status.pk, self.vm_status.pk)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
        self.assertTrue(now < vm_status.wait_time)

    @patch('vm_manager.views.django_rq')
    def test_supersize_vm_inconsistent(self, mock_rq):
        with self.assertRaises(Http404):
            supersize_vm(self.user, uuid.uuid4(), self.FEATURE)

        self.build_existing_vm(None)
        self.assertEqual(
            f"VMStatus for user {self.user}, feature {self.FEATURE}, "
            f"instance {self.instance.id} is missing. Cannot supersize VM.",
            supersize_vm(self.user, self.instance.id, self.FEATURE))

        for state in ALL_VM_STATES - {VM_OKAY}:
            self.build_existing_vm(state)
            self.assertEqual(
                f"VMStatus for user {self.user}, feature {self.FEATURE}, "
                f"instance {self.instance.id} is in wrong state ({state}). "
                "Cannot supersize VM.",
                supersize_vm(self.user, self.instance.id, self.FEATURE))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_supersize_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_OKAY)
        now = datetime.now(utc)

        self.assertEqual(
            f"Status of {self.UBUNTU.id} for {self.user} "
            f"is {VM_RESIZING}",
            supersize_vm(self.user, self.instance.id, self.FEATURE))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            supersize_vm_worker, instance=self.instance,
            desktop_type=self.UBUNTU)
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.UBUNTU)
        self.assertEqual(vm_status.pk, self.vm_status.pk)
        self.assertEqual(VM_RESIZING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
        self.assertTrue(now < vm_status.wait_time)

    @patch('vm_manager.views.django_rq')
    def test_downsize_vm_inconsistent(self, mock_rq):
        with self.assertRaises(Http404):
            downsize_vm(self.user, uuid.uuid4(), self.FEATURE)

        self.build_existing_vm(None)
        self.assertEqual(
            f"VMStatus for user {self.user}, feature {self.FEATURE}, "
            f"instance {self.instance.id} is missing. Cannot downsize VM.",
            downsize_vm(self.user, self.instance.id, self.FEATURE))

        for state in ALL_VM_STATES - {VM_SUPERSIZED}:
            self.build_existing_vm(state)
            self.assertEqual(
                f"VMStatus for user {self.user}, feature {self.FEATURE}, "
                f"instance {self.instance.id} is in wrong state ({state}). "
                "Cannot downsize VM.",
                downsize_vm(self.user, self.instance.id, self.FEATURE))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_downsize_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_SUPERSIZED)
        now = datetime.now(utc)

        self.assertEqual(
            f"Status of {self.UBUNTU.id} for {self.user} "
            f"is {VM_RESIZING}",
            downsize_vm(self.user, self.instance.id, self.FEATURE))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            downsize_vm_worker, instance=self.instance,
            desktop_type=self.UBUNTU)
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.UBUNTU)
        self.assertEqual(vm_status.pk, self.vm_status.pk)
        self.assertEqual(VM_RESIZING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
        self.assertTrue(now < vm_status.wait_time)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    def test_get_vm_state(self):
        self.build_existing_vm(None)
        self.assertEqual((NO_VM, "No VM", None),
                         get_vm_state(self.vm_status,
                                      self.user, self.UBUNTU))

        self.build_existing_vm(NO_VM)
        self.assertEqual((NO_VM, "No VM", None),
                         get_vm_state(self.vm_status,
                                      self.user, self.UBUNTU))

        self.build_existing_vm(VM_DELETED)
        self.assertEqual((NO_VM, "No VM", None),
                         get_vm_state(self.vm_status,
                                      self.user, self.UBUNTU))

        self.build_existing_vm(VM_ERROR)
        self.assertEqual((VM_ERROR, "VM has Errored", self.instance.id),
                         get_vm_state(self.vm_status,
                                      self.user, self.UBUNTU))

        vm_status = VMStatusFactory.create(
            status=VM_ERROR, user=self.user,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.FEATURE)
        self.assertEqual((VM_MISSING, "VM has Errored", None),
                         get_vm_state(vm_status, self.user, self.UBUNTU))

        vm_status = VMStatusFactory.create(
            status=VM_WAITING, user=self.user,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.FEATURE, wait_time=after_time(10))
        self.assertEqual((VM_WAITING, "9", None),
                         get_vm_state(vm_status, self.user, self.UBUNTU))

        # Timeout
        vm_status = VMStatusFactory.create(
            status=VM_WAITING, user=self.user,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.FEATURE,
            instance=self.instance, wait_time=datetime.now(utc))
        self.assertEqual((VM_ERROR, "Instance Not Ready", self.instance.id),
                         get_vm_state(vm_status, self.user, self.UBUNTU))

        # Timeout during expiry downsize
        resize = ResizeFactory.create(instance=self.instance, reverted=None)
        resize.set_expires(datetime.now(utc), stage=EXP_EXPIRING)
        vm_status = VMStatusFactory.create(
            status=VM_WAITING, user=self.user,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.FEATURE,
            instance=self.instance, wait_time=datetime.now(utc))
        self.assertEqual((VM_ERROR, "Instance Not Ready", self.instance.id),
                         get_vm_state(vm_status, self.user, self.UBUNTU))
        resize = Resize.objects.get(pk=resize.pk)
        self.assertIsNone(resize.reverted)
        self.assertEqual(EXP_EXPIRY_FAILED_RETRYABLE, resize.expiration.stage)

        # Timeout with no instance
        vm_status = VMStatusFactory.create(
            status=VM_WAITING, user=self.user,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.FEATURE,
            wait_time=datetime.now(utc))
        self.assertEqual((VM_MISSING, "VM has Errored", None),
                         get_vm_state(vm_status, self.user, self.UBUNTU))
        # Changes the state to VM_ERROR
        self.assertEqual(VM_ERROR,
                         VMStatus.objects.get(pk=vm_status.pk).status)

        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.return_value = Fake(status=SHUTDOWN)
        self.build_existing_vm(VM_OKAY)
        self.assertEqual((VM_SHUTDOWN, "VM Shutdown", self.instance.id),
                         get_vm_state(self.vm_status,
                                      self.user, self.UBUNTU))

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.models.Instance.get_url')
    @patch('vm_manager.views.InstanceExpiryPolicy')
    def test_get_vm_state_2(self, mock_policy_class, mock_get_url):
        url = "https://foo/bar"
        mock_get_url.return_value = url

        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.return_value = Fake(status=ACTIVE)

        # Not testing the expiration policy decisions
        mock_policy = Mock()
        mock_policy_class.return_value = mock_policy

        now = datetime.now(utc)
        mock_policy.permitted_extension.return_value = timedelta(days=2)
        mock_policy.new_expiry.return_value = now + timedelta(days=2)

        date1 = now + timedelta(days=1)
        date2 = now + timedelta(days=2)

        self.build_existing_vm(VM_OKAY, expires=date1)
        self.assertEqual((VM_OKAY,
                          {'url': url,
                           'extension': timedelta(days=2),
                           'expiration': self.instance.expiration,
                           'extended_expiration': date2
                          },
                          self.instance.id),
                         get_vm_state(self.vm_status,
                                      self.user, self.UBUNTU))

        for os_status in [BUILD, REBOOT, REBUILD, RESCUE]:   # just some
            fake_nectar.nova.servers.get.return_value = Fake(status=os_status)
            self.build_existing_vm("lalala")
            self.assertEqual((VM_ERROR, "Error at OpenStack level",
                              self.instance.id),
                             get_vm_state(self.vm_status,
                                          self.user, self.UBUNTU))
            instance = Instance.objects.get(pk=self.instance.pk)
            self.assertEqual(f"Error at OpenStack level. Status: {os_status}",
                             instance.error_message)
            self.assertIsNone(instance.boot_volume.error_message)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.models.Instance.get_url')
    @patch('vm_manager.views.BoostExpiryPolicy')
    def test_get_vm_state_3(self, mock_policy_class, mock_get_url):
        url = "https://foo/bar"
        mock_get_url.return_value = url

        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.return_value = Fake(status=ACTIVE)
        self.build_existing_vm(VM_SUPERSIZED)

        # Not testing the expiration policy decisions
        mock_policy = Mock()
        mock_policy_class.return_value = mock_policy

        now = datetime.now(utc)
        mock_policy.permitted_extension.return_value = timedelta(days=2)
        mock_policy.new_expiry.return_value = now + timedelta(days=2)

        date1 = now + timedelta(days=1)
        date2 = now + timedelta(days=2)
        resize = ResizeFactory.create(instance=self.instance)
        resize.set_expires(date1)

        res = get_vm_state(self.vm_status, self.user, self.UBUNTU)

        self.assertEqual(
            (VM_SUPERSIZED,
             {'url': url,
              'extension': timedelta(days=2),
              'expiration': resize.expiration,
              'extended_expiration': date2
             },
             self.instance.id),
            get_vm_state(self.vm_status, self.user, self.UBUNTU))

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.views.VolumeExpiryPolicy')
    def test_get_vm_state_4(self, mock_policy_class):

        # Not testing the expiration policy decisions
        mock_policy = Mock()
        mock_policy_class.return_value = mock_policy

        now = datetime.now(utc)
        mock_policy.permitted_extension.return_value = timedelta(days=2)
        mock_policy.new_expiry.return_value = now + timedelta(days=2)

        date1 = now + timedelta(days=1)
        date2 = now + timedelta(days=2)

        self.build_existing_vm(VM_SHELVED, volume_expires=date1)
        self.assertEqual((VM_SHELVED,
                          {'url': None,
                           'extension': timedelta(days=2),
                           'expiration': self.volume.expiration,
                           'extended_expiration': date2
                          },
                          self.instance.id),
                         get_vm_state(self.vm_status,
                                      self.user, self.UBUNTU))

    @patch('vm_manager.views.loader')
    @patch('vm_manager.models.Instance.get_url')
    @patch('vm_manager.views.messages')
    @patch('vm_manager.views.InstanceExpiryPolicy')
    def test_render_vm_okay(self, mock_policy_class, mock_messages,
                            mock_get_url, mock_loader):
        url = "https://foo/bar"
        mock_get_url.return_value = url

        # Not testing what is actually rendered.
        mock_loader.render_to_string.return_value = "rendered"

        # Not testing the expiration policy decisions
        mock_policy = Mock()
        mock_policy_class.return_value = mock_policy
        now = datetime.now(utc)
        date1 = now + timedelta(days=7)
        date2 = now + timedelta(days=7)

        mock_policy.permitted_extension.return_value = \
            timedelta(days=7)
        mock_policy.new_expiry.return_value = \
            now + timedelta(days=7)

        request = "The Request"
        buttons = ["ONE", "TWO", EXTEND_BUTTON,
                   EXTEND_BOOST_BUTTON, BOOST_BUTTON]

        self.build_existing_vm(VM_OKAY, expires=date1, stage=EXP_FIRST_WARNING)
        self.assertEqual(("rendered", "rendered", "rendered", VM_OKAY),
                         render_vm(request, self.user, self.UBUNTU,
                                   buttons))
        context = {
            'state': VM_OKAY,
            'what_to_show': {
                'url': url,
                'extension': timedelta(days=settings.BOOST_EXTENSION),
                'expiration': self.instance.expiration,
                'extended_expiration': date2},
            'desktop_type': self.UBUNTU,
            'vm_id': self.instance.id,
            'buttons_to_display': ['ONE', 'TWO', EXTEND_BUTTON, BOOST_BUTTON],
            'app_name': self.FEATURE.app_name,
            'requesting_feature': self.FEATURE,
            'vm_status': self.vm_status,
        }
        calls = [call(f"vm_manager/html/{VM_OKAY}.html",
                      context, request),
                 call(f"vm_manager/javascript/{VM_OKAY}.js",
                      context, request),
                 call(f"vm_manager/html/{NO_VM}.html",
                      context, request), ]
        mock_policy.permitted_extension.assert_called_once_with(self.instance)
        mock_policy.new_expiry.assert_called_once_with(self.instance)
        mock_loader.render_to_string.assert_has_calls(calls)
        mock_messages.info.assert_called_once_with(
            'The Request',
            f'Your {self.UBUNTU.name} desktop is set to be shelved '
            '6\xa0days, 23\xa0hours from now')

    @patch('vm_manager.views.loader')
    @patch('vm_manager.models.Instance.get_url')
    @patch('vm_manager.views.messages')
    @patch('vm_manager.views.InstanceExpiryPolicy')
    def test_render_no_vm(self, mock_policy_class, mock_messages,
                          mock_get_url, mock_loader):
        url = "https://foo/bar"
        mock_get_url.return_value = url

        # Not testing what is actually rendered.
        mock_loader.render_to_string.return_value = "rendered"

        request = "The Request"
        buttons = ["ONE", "TWO", EXTEND_BUTTON,
                   EXTEND_BOOST_BUTTON, BOOST_BUTTON]

        self.assertEqual(("rendered", "rendered", "rendered", NO_VM),
                         render_vm(request, self.user, self.UBUNTU,
                                   buttons))
        context = {
            'state': NO_VM,
            'what_to_show': 'No VM',
            'desktop_type': self.UBUNTU,
            'vm_id': None,
            'buttons_to_display': [
                'ONE', 'TWO', EXTEND_BUTTON, EXTEND_BOOST_BUTTON,
                BOOST_BUTTON],
            'app_name': self.FEATURE.app_name,
            'requesting_feature': self.FEATURE,
            'vm_status': None,
        }
        calls = [call(f"vm_manager/html/{NO_VM}.html",
                      context, request),
                 call(f"vm_manager/javascript/{NO_VM}.js",
                      context, request), ]
        mock_loader.render_to_string.assert_has_calls(calls)
        mock_messages.info.assert_not_called()

    @patch('vm_manager.views.loader')
    @patch('vm_manager.models.Instance.get_url')
    @patch('vm_manager.views.messages')
    @patch('vm_manager.views.BoostExpiryPolicy')
    def test_render_vm_supersized(self, mock_policy_class, mock_messages,
                                  mock_get_url, mock_loader):
        url = "https://foo/bar"
        mock_get_url.return_value = url

        # Not testing what is actually rendered.
        mock_loader.render_to_string.return_value = "rendered"

        # Not testing the expiration policy decisions
        mock_policy = Mock()
        mock_policy_class.return_value = mock_policy

        self.build_existing_vm(VM_SUPERSIZED)
        now = datetime.now(utc)
        date1 = now + timedelta(days=7)
        date2 = now + timedelta(days=7)
        resize = ResizeFactory.create(instance=self.instance)
        resize.set_expires(date1, stage=EXP_FIRST_WARNING)

        mock_policy.permitted_extension.return_value = timedelta(days=7)
        mock_policy.new_expiry.return_value = now + timedelta(days=7)

        request = "The Request"
        buttons = ["ONE", "TWO", EXTEND_BUTTON,
                   EXTEND_BOOST_BUTTON, BOOST_BUTTON]
        self.assertEqual(("rendered", "rendered", "rendered", VM_SUPERSIZED),
                         render_vm(request, self.user, self.UBUNTU,
                                   buttons))
        context = {
            'state': VM_SUPERSIZED,
            'what_to_show': {
                'url': url,
                'extension': timedelta(days=settings.BOOST_EXTENSION),
                'expiration': resize.expiration,
                'extended_expiration': date2},
            'desktop_type': self.UBUNTU,
            'vm_id': self.instance.id,
            'buttons_to_display': ['ONE', 'TWO', EXTEND_BOOST_BUTTON],
            'app_name': self.FEATURE.app_name,
            'requesting_feature': self.FEATURE,
            'vm_status': self.vm_status,
        }
        calls = [call(f"vm_manager/html/{VM_SUPERSIZED}.html",
                      context, request),
                 call(f"vm_manager/javascript/{VM_SUPERSIZED}.js",
                      context, request)]
        mock_policy.permitted_extension.assert_called_once_with(resize)
        mock_policy.new_expiry.assert_called_once_with(resize)
        mock_loader.render_to_string.assert_has_calls(calls)
        mock_messages.info.assert_called_once_with(
            'The Request',
            f'Your {self.UBUNTU.name} desktop is set to be resized to '
            'the default size 6\xa0days, 23\xa0hours from now')

        # Reset for supersized (not allowed)
        mock_policy.permitted_extension.reset_mock()
        mock_policy.new_expiry.reset_mock()
        mock_loader.render_to_string.reset_mock()
        mock_messages.info.reset_mock()

        mock_policy.permitted_extension.return_value = timedelta(seconds=0)
        mock_policy.new_expiry.return_value = date1

        self.assertEqual(("rendered", "rendered", "rendered", VM_SUPERSIZED),
                         render_vm(request, self.user, self.UBUNTU,
                                   buttons))
        context['what_to_show'] = {
            'url': url,
            'extension': timedelta(seconds=0),
            'expiration': resize.expiration,
            'extended_expiration': date1
        }
        context['buttons_to_display'] = ['ONE', 'TWO']
        calls = [call(f"vm_manager/html/{VM_SUPERSIZED}.html",
                      context, request),
                 call(f"vm_manager/javascript/{VM_SUPERSIZED}.js",
                      context, request)]
        mock_policy.permitted_extension.assert_called_once_with(resize)
        mock_policy.new_expiry.assert_called_once_with(resize)
        mock_loader.render_to_string.assert_has_calls(calls)
        mock_messages.info.assert_called_once_with(
            'The Request',
            f'Your {self.UBUNTU.name} desktop is set to be resized to '
            'the default size 6\xa0days, 23\xa0hours from now')

    @patch('vm_manager.views.logger')
    @patch('vm_manager.views.generate_hostname')
    def test_notify_vm(self, mock_gen, mock_logger):
        fake_request = Fake(GET={
            'ip': '10.0.0.1',
            'hn': 'foo',
            'os': self.UBUNTU.id,
            'state': SCRIPT_OKAY,
            'msg': CLOUD_INIT_STARTED
        })
        with self.assertRaises(Http404):
            notify_vm(fake_request, self.FEATURE)
        mock_logger.error.assert_called_with(
            "No current Instance found with IP address 10.0.0.1")

        mock_gen.return_value = "bzzzt"
        self.build_existing_vm(VM_WAITING)
        with self.assertRaises(Http404):
            notify_vm(fake_request, self.FEATURE)
        mock_logger.error.assert_called_with(
            "Hostname provided in request does not match "
            f"hostname of volume {self.instance}, foo")
        mock_gen.assert_called_with(
            self.volume.hostname_id, self.UBUNTU.id)

        mock_gen.reset_mock()
        mock_logger.error.reset_mock()
        mock_gen.return_value = "foo"

        self.assertEqual(
            f"{self.instance.ip_address}, {self.UBUNTU.id}, "
            f"{SCRIPT_OKAY}, {CLOUD_INIT_STARTED}",
            notify_vm(fake_request, self.FEATURE))

        mock_gen.assert_called_with(
            self.volume.hostname_id, self.UBUNTU.id)
        mock_logger.error.assert_not_called()
        volume = Volume.objects.get(pk=self.volume.pk)
        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertTrue(volume.checked_in)
        self.assertFalse(volume.ready)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)  # unchanged

        mock_gen.reset_mock()
        mock_logger.error.reset_mock()
        fake_request = Fake(GET={
            'ip': '10.0.0.1',
            'hn': 'foo',
            'os': self.UBUNTU.id,
            'state': SCRIPT_OKAY,
            'msg': CLOUD_INIT_FINISHED
        })

        self.assertEqual(
            f"{self.instance.ip_address}, {self.UBUNTU.id}, "
            f"{SCRIPT_OKAY}, {CLOUD_INIT_FINISHED}",
            notify_vm(fake_request, self.FEATURE))

        mock_gen.assert_called_with(
            self.volume.hostname_id, self.UBUNTU.id)
        mock_logger.error.assert_not_called()
        volume = Volume.objects.get(pk=self.volume.pk)
        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertTrue(volume.checked_in)
        self.assertTrue(volume.ready)
        self.assertEqual(VM_OKAY, vm_status.status)
        self.assertEqual(100, vm_status.status_progress)

        mock_gen.reset_mock()
        mock_logger.error.reset_mock()
        fake_request = Fake(GET={
            'ip': '10.0.0.1',
            'hn': 'foo',
            'os': self.UBUNTU.id,
            'state': 42,
            'msg': "Other Message"
        })

        self.assertEqual(
            f"{self.instance.ip_address}, {self.UBUNTU.id}, "
            "42, Other Message",
            notify_vm(fake_request, self.FEATURE))

        mock_gen.assert_called_with(
            self.volume.hostname_id, self.UBUNTU.id)
        mock_logger.error.assert_called_with(
            "Notify VM Error: Other Message for instance: "
            f"\"{self.instance}\"")
        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertEqual(VM_ERROR, vm_status.status)
        self.assertEqual("Other Message", vm_status.instance.error_message)

    @patch('vm_manager.views.logger')
    @patch('vm_manager.models.logger')
    @patch('vm_manager.views.generate_hostname')
    def test_phone_home(self, mock_gen, mock_logger_2, mock_logger):
        now = datetime.now(utc)

        # No id in POST data
        fake_request = Fake(POST={})
        with self.assertRaises(Http404):
            phone_home(fake_request, self.FEATURE)
        mock_logger.error.assert_called_with("Instance ID not found in data")

        # Unknown instance id
        fake_id = uuid.uuid4()
        fake_request = Fake(POST={'instance_id': fake_id})
        with self.assertRaises(Http404):
            phone_home(fake_request, self.FEATURE)
        mock_logger_2.error.assert_called_with(
            "Trying to get a vm that doesn't exist with vm_id: "
            f"{fake_id}, called by internal")

        # Unexpected phone home: instance already OKAY.  (This would
        # happen if an instance was rebooted from Openstack side w/o
        # Bumblebee's involvement.)
        self.build_existing_vm(VM_OKAY)
        fake_request = Fake(POST={'instance_id': self.instance.id})
        self.assertEqual(
            f"Unexpected phone home for {self.instance}. "
            f"VM_status is {self.vm_status}",
            phone_home(fake_request, self.FEATURE))

        # Normal phone home
        self.build_existing_vm(VM_WAITING)
        fake_request = Fake(POST={'instance_id': self.instance.id})
        self.assertEqual(
            f"Phone home for {self.instance} - success!",
            phone_home(fake_request, self.FEATURE))
        volume = Volume.objects.get(pk=self.volume.pk)
        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertTrue(volume.ready)
        self.assertEqual(VM_OKAY, vm_status.status)
        self.assertEqual(100, vm_status.status_progress)

        # Phone home for boosted instance
        self.build_existing_vm(VM_WAITING)
        resize = ResizeFactory.create(instance=self.instance)
        fake_request = Fake(POST={'instance_id': self.instance.id})
        self.assertEqual(
            f"Phone home for {self.instance} - success!",
            phone_home(fake_request, self.FEATURE))
        volume = Volume.objects.get(pk=self.volume.pk)
        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertTrue(volume.ready)
        self.assertEqual(VM_SUPERSIZED, vm_status.status)
        self.assertEqual(100, vm_status.status_progress)

        # Phone home following downsize
        self.build_existing_vm(VM_WAITING)
        resize = ResizeFactory.create(instance=self.instance, reverted=now)
        fake_request = Fake(POST={'instance_id': self.instance.id})
        self.assertEqual(
            f"Phone home for {self.instance} - success!",
            phone_home(fake_request, self.FEATURE))
        volume = Volume.objects.get(pk=self.volume.pk)
        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertTrue(volume.ready)
        self.assertEqual(VM_OKAY, vm_status.status)
        self.assertEqual(100, vm_status.status_progress)

        # Phone home following expirer downsize
        self.build_existing_vm(VM_WAITING)
        resize = ResizeFactory.create(instance=self.instance, reverted=now)
        resize.set_expires(now, EXP_EXPIRING)
        fake_request = Fake(POST={'instance_id': self.instance.id})
        self.assertEqual(
            f"Phone home for {self.instance} - success!",
            phone_home(fake_request, self.FEATURE))
        volume = Volume.objects.get(pk=self.volume.pk)
        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertTrue(volume.ready)
        self.assertEqual(VM_OKAY, vm_status.status)
        self.assertEqual(100, vm_status.status_progress)
        resize = Resize.objects.get(pk=resize.pk)
        expiration = Expiration.objects.get(pk=resize.expiration.pk)
        self.assertEqual(EXP_EXPIRY_COMPLETED, expiration.stage)
        self.assertTrue(now < expiration.stage_date)

        # Late phone home
        self.build_existing_vm(VM_ERROR)
        fake_request = Fake(POST={'instance_id': self.instance.id})
        self.assertEqual(
            f"Phone home for {self.instance} - success!",
            phone_home(fake_request, self.FEATURE))

    @patch('vm_manager.views.datetime')
    def test_rd_report_for_user(self, mock_datetime):
        # Freeze time ...
        now = datetime.now(utc)
        mock_datetime.now.return_value = now

        dt_1 = DesktopTypeFactory.create(
            feature=self.FEATURE, id='dt1', name='desktop one')
        dt_2 = DesktopTypeFactory.create(
            feature=self.FEATURE, id='dt2', name='desktop two')
        dt_ids = ['dt1', 'dt2']
        volume_1 = VolumeFactory.create(
            operating_system=dt_1.id, requesting_feature=self.FEATURE,
            id=uuid.uuid4(), user=self.user)
        volume_2 = VolumeFactory.create(
            operating_system=dt_2.id, requesting_feature=self.FEATURE,
            id=uuid.uuid4(), user=self.user)

        self.assertEqual(
            {
                'user_vm_info': {
                'dt1': [{'count': 0, 'date': now}],
                'dt2': [{'count': 0, 'date': now}]
                }
            },
            rd_report_for_user(self.user, dt_ids, self.FEATURE)
        )

        yesterday = now - timedelta(days=1)
        instance_1 = InstanceFactory.create(
            id=uuid.uuid4(), created=yesterday, boot_volume=volume_1,
            user=self.user)

        self._compare_graphs(
            {
                'user_vm_info': {
                    'dt1': [{'count': 0, 'date': yesterday},
                            {'count': 1, 'date': yesterday},
                            {'count': 1, 'date': now}],
                    'dt2': [{'count': 0, 'date': now}]
                }
            },
            rd_report_for_user(self.user, dt_ids, self.FEATURE))

        yesterday_plus_one_hour = yesterday + timedelta(hours=1)
        yesterday_plus_two_hours = yesterday + timedelta(hours=2)
        instance_2 = InstanceFactory.create(
            id=uuid.uuid4(),
            created=yesterday_plus_one_hour,
            marked_for_deletion=yesterday_plus_two_hours,
            boot_volume=volume_1,
            user=self.user)

        self._compare_graphs(
            {
                'user_vm_info': {
                    'dt1': [{'count': 0, 'date': yesterday},
                            {'count': 1, 'date': yesterday},
                            {'count': 1, 'date': yesterday_plus_one_hour},
                            {'count': 2, 'date': yesterday_plus_one_hour},
                            {'count': 2, 'date': yesterday_plus_two_hours},
                            {'count': 1, 'date': yesterday_plus_two_hours},
                            {'count': 1, 'date': now}],
                    'dt2': [{'count': 0, 'date': now}]
                }
            },
            rd_report_for_user(self.user, dt_ids, self.FEATURE))

    def _compare_graphs(self, expected, actual):
        self.assertEqual(expected['user_vm_info'].keys(),
                         actual['user_vm_info'].keys())
        for key in expected['user_vm_info'].keys():
            e_graph = expected['user_vm_info'][key]
            a_graph = actual['user_vm_info'][key]
            self.assertEqual(len(e_graph), len(a_graph))
            for i in range(0, len(e_graph) - 1):
                self.assertEqual(e_graph[i]['count'], e_graph[i]['count'],
                                 f"counts for {key}[{i}] differ")
                self.assertEqual(e_graph[i]['date'].timestamp(),
                                 e_graph[i]['date'].timestamp(),
                                 f"timestamps for {key}[{i}] differ")

    @patch('vm_manager.views.logger')
    def test_delete_shelved_vm_inconsistent(self, mock_logger):
        self.assertEqual(
            f"VMStatus for user {self.user}, "
            f"desktop_type {self.UBUNTU.id} "
            "is missing. Cannot delete shelved VM.",
            delete_shelved_vm(self.user, self.UBUNTU))

        self.build_existing_vm(None)

        for status in ALL_VM_STATES - {VM_SHELVED}:
            self.build_existing_vm(status)
            self.assertEqual(
                f"VMStatus for user {self.user}, "
                f"desktop_type {self.UBUNTU.id}, "
                f"instance {self.instance.id} "
                f"is in wrong state ({status}). Cannot delete shelved VM.",
                delete_shelved_vm(self.user, self.UBUNTU))

        mock_logger.error.reset_mock()
        self.build_existing_vm(VM_SHELVED)
        self.assertEqual(
            f"Status of {self.UBUNTU.id} for {self.user} "
            f"is {VM_SHELVED}",
            delete_shelved_vm(self.user, self.UBUNTU))
        mock_logger.error.assert_called_once_with(
            f"Instance still exists for shelved {self.UBUNTU.id}, "
            f"vm_status: Status of {self.UBUNTU.id} for {self.user} "
            f"is {VM_SHELVED}")

    @patch('vm_manager.views.logger')
    @patch('vm_manager.views.delete_volume_worker')
    def test_delete_shelved_vm(self, mock_delete, mock_logger):
        self.build_existing_vm(VM_SHELVED)
        self.instance.deleted = datetime.now(utc)
        self.instance.save()

        self.assertEqual(
            f"Status of {self.UBUNTU.id} for {self.user} "
            f"is {VM_DELETED}",
            delete_shelved_vm(self.user, self.UBUNTU))
        mock_logger.error.assert_not_called()
        mock_logger.info.assert_called_once_with(
            f"Deleting shelved volume {self.volume}")
        mock_delete.assert_called_once_with(self.volume)
