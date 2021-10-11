import uuid
import copy
from datetime import datetime, timedelta, timezone

from unittest.mock import Mock, patch

from django.conf import settings
from django.http import Http404
from django.test import TestCase

from researcher_workspace.settings import GUACAMOLE_URL
from researcher_workspace.tests.factories import FeatureFactory, UserFactory
from researcher_desktop.tests.factories import DesktopTypeFactory
from vm_manager.tests.factories import InstanceFactory, VolumeFactory, \
    ResizeFactory, VMStatusFactory
from vm_manager.tests.fakes import Fake, FakeNectar

from vm_manager.constants import ERROR, ACTIVE, SHUTDOWN, VERIFY_RESIZE, \
    BUILD, REBUILD, RESIZE, REBOOT, RESCUE, REBOOT_HARD, REBOOT_SOFT

from vm_manager.constants import VM_OKAY, VM_DELETED, VM_WAITING, \
    VM_CREATING, VM_RESIZING, NO_VM, VM_SHELVED, VM_MISSING, VM_ERROR, \
    VM_SHUTDOWN, VM_SUPERSIZED, ALL_VM_STATES, LAUNCH_WAIT_SECONDS, \
    DOWNSIZE_PERIOD
from vm_manager.models import VMStatus, Instance
from vm_manager.utils.utils import get_nectar, after_time
from vm_manager.views import launch_vm_worker, delete_vm_worker, \
    shelve_vm_worker, unshelve_vm_worker, reboot_vm_worker, supersize_vm_worker, \
    downsize_vm_worker

from vm_manager.views import launch_vm, delete_vm, shelve_vm, unshelve_vm, \
    reboot_vm, supersize_vm, downsize_vm, get_vm_state


class VMManagerViewTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()
        self.feature = FeatureFactory.create(name='feature',
                                             app_name='feature_app')
        self.desktop_type = DesktopTypeFactory.create(name='some desktop',
                                                      id='desktop',
                                                      feature=self.feature)

    def build_existing_vm(self, status):
        self.volume = VolumeFactory.create(
            id=uuid.uuid4(), user=self.user,
            requesting_feature=self.feature)
        self.instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=self.volume,
            ip_address='10.0.0.1')
        if status:
            self.vm_status = VMStatusFactory.create(
                instance=self.instance,
                user=self.user,
                operating_system=self.desktop_type.id,
                requesting_feature=self.feature,
                status=status)
        else:
            self.vm_status = None

    @patch('vm_manager.views.django_rq')
    def test_launch_vm_exists(self, mock_rq):
        self.build_existing_vm(VM_OKAY)
        self.assertEqual(
            f"VMStatus for user {self.user}, desktop_type {self.desktop_type.id}, "
            f"instance {self.instance.id} is in wrong state "
            f"({self.vm_status.status}). Cannot launch VM.",
            launch_vm(self.user, self.desktop_type))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_launch_vm(self, mock_rq):
        self.build_existing_vm(VM_DELETED)

        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        now = datetime.now(timezone.utc)

        self.assertEqual(
            f"Status of [feature][desktop][{self.user}] "
            f"is {VM_WAITING}",
            launch_vm(self.user, self.desktop_type))
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.desktop_type)
        self.assertTrue(vm_status != self.vm_status)
        self.assertEqual(VM_CREATING, vm_status.status)
        self.assertEqual(self.desktop_type.id, vm_status.operating_system)
        self.assertEqual(self.feature, vm_status.requesting_feature)
        self.assertTrue(now <= vm_status.created)
        self.assertTrue(after_time(LAUNCH_WAIT_SECONDS)
                        >= vm_status.wait_time)

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            launch_vm_worker, user=self.user, desktop_type=self.desktop_type)

    @patch('vm_manager.views.django_rq')
    def test_delete_vm_inconsistent(self, mock_rq):
        with self.assertRaises(Http404):
            delete_vm(self.user, uuid.uuid4(), self.feature)

        self.build_existing_vm(None)
        self.assertEqual(
            f"VMStatus for user {self.user}, feature {self.feature} "
            f"is missing. Cannot delete VM.",
            delete_vm(self.user, self.instance.id, self.feature))

        self.build_existing_vm(NO_VM)
        self.assertEqual(
            f"VMStatus for user {self.user}, feature {self.feature}, "
            f"instance {self.instance.id} is in wrong state ({NO_VM}). "
            f"Cannot delete VM.",
            delete_vm(self.user, self.instance.id, self.feature))

        self.build_existing_vm(VM_DELETED)
        self.assertEqual(
            f"VMStatus for user {self.user}, feature {self.feature}, "
            f"instance {self.instance.id} is in wrong state ({VM_DELETED}). "
            f"Cannot delete VM.",
            delete_vm(self.user, self.instance.id, self.feature))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_delete_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue

        self.build_existing_vm(VM_OKAY)
        self.assertEqual(
            f"Status of [{self.feature}][{self.desktop_type.id}]"
            f"[{self.user}] is {NO_VM}",
            delete_vm(self.user, self.instance.id, self.feature))

        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertEqual(VM_DELETED, vm_status.status)
        self.assertIsNotNone(vm_status.instance.marked_for_deletion)
        self.assertIsNotNone(vm_status.instance.boot_volume.marked_for_deletion)

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            delete_vm_worker, self.instance)

    @patch('vm_manager.views.django_rq')
    def test_shelve_vm_inconsistent(self, mock_rq):
        with self.assertRaises(Http404):
            shelve_vm(self.user, uuid.uuid4(), self.feature)

        self.build_existing_vm(None)
        self.assertEqual(
            f"VMStatus for user {self.user}, "
            f"feature {self.feature}, instance {self.instance.id} "
            f"is missing. Cannot shelve VM.",
            shelve_vm(self.user, self.instance.id, self.feature))

        for status in ALL_VM_STATES - {VM_OKAY, VM_SUPERSIZED}:
            self.build_existing_vm(status)
            self.assertEqual(
                f"VMStatus for user {self.user}, "
                f"feature {self.feature}, instance {self.instance.id} "
                f"is in wrong state ({status}). Cannot shelve VM.",
                shelve_vm(self.user, self.instance.id, self.feature))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_shelve_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_OKAY)

        self.assertEqual(
            f"Status of [{self.feature}][{self.desktop_type.id}][{self.user}] "
            f"is {VM_WAITING}",
            shelve_vm(self.user, self.instance.id, self.feature))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            shelve_vm_worker, self.instance, self.feature)
        vm_status = VMStatus.objects.get(pk=self.vm_status.id)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertIsNotNone(vm_status.instance.marked_for_deletion)
        self.assertIsNone(vm_status.instance.boot_volume.marked_for_deletion)

    @patch('vm_manager.views.django_rq')
    def test_unshelve_vm_inconsistent(self, mock_rq):
        self.assertEqual(
            f"VMStatus for user {self.user}, "
            f"desktop_type {self.desktop_type.id} "
            f"is missing. Cannot unshelve VM.",
            unshelve_vm(self.user, self.desktop_type))

        self.build_existing_vm(None)

        for status in ALL_VM_STATES - {VM_SHELVED}:
            self.build_existing_vm(status)
            self.assertEqual(
                f"VMStatus for user {self.user}, "
                f"desktop_type {self.desktop_type.id}, "
                f"instance {self.instance.id} "
                f"is in wrong state ({status}). Cannot unshelve VM.",
                unshelve_vm(self.user, self.desktop_type))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_unshelve_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_SHELVED)

        self.assertEqual(
            f"Status of [{self.feature}][{self.desktop_type.id}][{self.user}] "
            f"is {VM_CREATING}",
            unshelve_vm(self.user, self.desktop_type))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            unshelve_vm_worker, user=self.user, desktop_type=self.desktop_type)
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.desktop_type)
        self.assertTrue(vm_status.pk != self.vm_status.pk)
        self.assertEqual(VM_CREATING, vm_status.status)
        self.assertIsNone(vm_status.instance)
        self.assertEqual(vm_status.operating_system, self.desktop_type.id)
        self.assertEqual(vm_status.requesting_feature, self.feature)

    @patch('vm_manager.views.django_rq')
    def test_reboot_vm_inconsistent(self, mock_rq):
        with self.assertRaises(Http404):
            reboot_vm(self.user, uuid.uuid4(), REBOOT_SOFT, self.feature)

        self.build_existing_vm(None)
        with self.assertRaises(VMStatus.DoesNotExist):
            reboot_vm(self.user, self.instance.id, REBOOT_SOFT, self.feature)

        for status in ALL_VM_STATES - {VM_OKAY, VM_SUPERSIZED}:
            self.build_existing_vm(status)
            self.assertEqual(
                f"VMStatus for user {self.user}, feature {self.feature}, "
                f"instance {self.instance.id} is in wrong state ({status}). "
                f"Cannot reboot VM.",
                reboot_vm(self.user, self.instance.id, REBOOT_SOFT, self.feature))

        self.build_existing_vm(VM_OKAY)
        with self.assertRaises(Http404):
            reboot_vm(self.user, self.instance.id, "squirrelly", self.feature)

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_reboot_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_OKAY)
        now = datetime.now(timezone.utc)

        self.assertEqual(
            f"Status of [{self.feature}][{self.desktop_type.id}][{self.user}] "
            f"is {VM_OKAY}",
            reboot_vm(self.user, self.instance.id, REBOOT_SOFT, self.feature))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            reboot_vm_worker, self.user, self.instance.id, REBOOT_SOFT,
            self.feature)
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.desktop_type)
        self.assertEqual(vm_status.pk, self.vm_status.pk)
        self.assertEqual(VM_OKAY, vm_status.status)
        self.assertTrue(now < vm_status.wait_time)

    @patch('vm_manager.views.django_rq')
    def test_supersize_vm_inconsistent(self, mock_rq):
        with self.assertRaises(Http404):
            supersize_vm(self.user, uuid.uuid4(), self.feature)

        self.build_existing_vm(None)
        self.assertEqual(
            f"VMStatus for user {self.user}, feature {self.feature}, "
            f"instance {self.instance.id} is missing. Cannot supersize VM.",
            supersize_vm(self.user, self.instance.id, self.feature))

        for state in ALL_VM_STATES - {VM_OKAY}:
            self.build_existing_vm(state)
            self.assertEqual(
                f"VMStatus for user {self.user}, feature {self.feature}, "
                f"instance {self.instance.id} is in wrong state ({state}). "
                f"Cannot supersize VM.",
                supersize_vm(self.user, self.instance.id, self.feature))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_supersize_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_OKAY)
        now = datetime.now(timezone.utc)

        self.assertEqual(
            f"Status of [{self.feature}][{self.desktop_type.id}][{self.user}] "
            f"is {VM_RESIZING}",
            supersize_vm(self.user, self.instance.id, self.feature))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            supersize_vm_worker, instance=self.instance,
            desktop_type=self.desktop_type)
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.desktop_type)
        self.assertEqual(vm_status.pk, self.vm_status.pk)
        self.assertEqual(VM_RESIZING, vm_status.status)
        self.assertTrue(now < vm_status.wait_time)

    @patch('vm_manager.views.django_rq')
    def test_downsize_vm_inconsistent(self, mock_rq):
        with self.assertRaises(Http404):
            downsize_vm(self.user, uuid.uuid4(), self.feature)

        self.build_existing_vm(None)
        self.assertEqual(
            f"VMStatus for user {self.user}, feature {self.feature}, "
            f"instance {self.instance.id} is missing. Cannot downsize VM.",
            downsize_vm(self.user, self.instance.id, self.feature))

        for state in ALL_VM_STATES - {VM_SUPERSIZED}:
            self.build_existing_vm(state)
            self.assertEqual(
                f"VMStatus for user {self.user}, feature {self.feature}, "
                f"instance {self.instance.id} is in wrong state ({state}). "
                f"Cannot downsize VM.",
                downsize_vm(self.user, self.instance.id, self.feature))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_downsize_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_SUPERSIZED)
        now = datetime.now(timezone.utc)

        self.assertEqual(
            f"Status of [{self.feature}][{self.desktop_type.id}][{self.user}] "
            f"is {VM_RESIZING}",
            downsize_vm(self.user, self.instance.id, self.feature))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            downsize_vm_worker, instance=self.instance,
            desktop_type=self.desktop_type)
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.desktop_type)
        self.assertEqual(vm_status.pk, self.vm_status.pk)
        self.assertEqual(VM_RESIZING, vm_status.status)
        self.assertTrue(now < vm_status.wait_time)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.models.Instance.get_url')
    def test_get_vm_state_2(self, mock_get_url):
        self.assertEqual((NO_VM, "No VM", None),
                         get_vm_state(self.user, self.desktop_type))

        self.build_existing_vm(None)
        self.assertEqual((NO_VM, "No VM", None),
                         get_vm_state(self.user, self.desktop_type))

        self.build_existing_vm(NO_VM)
        self.assertEqual((NO_VM, "No VM", None),
                         get_vm_state(self.user, self.desktop_type))

        self.build_existing_vm(VM_DELETED)
        self.assertEqual((NO_VM, "No VM", None),
                         get_vm_state(self.user, self.desktop_type))

        self.build_existing_vm(VM_ERROR)
        self.assertEqual((VM_ERROR, "VM has Errored", self.instance.id),
                         get_vm_state(self.user, self.desktop_type))

        VMStatusFactory.create(
            status=VM_ERROR, user=self.user,
            operating_system=self.desktop_type.id,
            requesting_feature=self.feature)
        self.assertEqual((VM_MISSING, "VM has Errored", None),
                         get_vm_state(self.user, self.desktop_type))

        VMStatusFactory.create(
            status=VM_WAITING, user=self.user,
            operating_system=self.desktop_type.id,
            requesting_feature=self.feature, wait_time=after_time(10))
        self.assertEqual((VM_WAITING, "9", None),
                         get_vm_state(self.user, self.desktop_type))

        VMStatusFactory.create(
            status=VM_WAITING, user=self.user,
            operating_system=self.desktop_type.id,
            requesting_feature=self.feature,
            instance=self.instance, wait_time=datetime.now(timezone.utc))
        self.assertEqual((VM_ERROR, "VM Not Ready", self.instance.id),
                         get_vm_state(self.user, self.desktop_type))

        vm_status = VMStatusFactory.create(
            status=VM_WAITING, user=self.user,
            operating_system=self.desktop_type.id,
            requesting_feature=self.feature,
            wait_time=datetime.now(timezone.utc))
        self.assertEqual((VM_MISSING, "VM has Errored", None),
                         get_vm_state(self.user, self.desktop_type))
        # Changes the state to VM_ERROR
        self.assertEqual(VM_ERROR,
                         VMStatus.objects.get(pk=vm_status.pk).status)

        self.build_existing_vm(VM_SHELVED)
        self.assertEqual((VM_SHELVED, "VM SHELVED", self.instance.id),
                         get_vm_state(self.user, self.desktop_type))

        fake_nectar = get_nectar()
        fake_nectar.nova.servers.get.return_value = Fake(status=SHUTDOWN)
        self.build_existing_vm(VM_OKAY)
        self.assertEqual((VM_SHUTDOWN, "VM Shutdown", self.instance.id),
                         get_vm_state(self.user, self.desktop_type))

        url = "https://foo/bar"
        mock_get_url.return_value = url

        fake_nectar.nova.servers.get.return_value = Fake(status=ACTIVE)
        self.build_existing_vm(VM_OKAY)
        self.assertEqual((VM_OKAY, {'url': url}, self.instance.id),
                         get_vm_state(self.user, self.desktop_type))

        for os_status in [BUILD, REBOOT, REBUILD, RESCUE]:   # just some
            fake_nectar.nova.servers.get.return_value = Fake(status=os_status)
            self.build_existing_vm("lalala")
            self.assertEqual((VM_ERROR, "Error at OpenStack level",
                              self.instance.id),
                             get_vm_state(self.user, self.desktop_type))
            instance = Instance.objects.get(pk=self.instance.pk)
            self.assertEqual(f"Error at OpenStack level. Status: {os_status}",
                             instance.error_message)
            self.assertIsNone(instance.boot_volume.error_message)

        fake_nectar.nova.servers.get.return_value = Fake(status=ACTIVE)
        self.build_existing_vm(VM_SUPERSIZED)
        time1 = (datetime.now(timezone.utc)
                 + timedelta(days=DOWNSIZE_PERIOD)).date()
        time2 = (datetime.now(timezone.utc)
                 + timedelta(days=(DOWNSIZE_PERIOD * 2))).date()
        resize = ResizeFactory.create(instance=self.instance, expires=time1)
        self.assertEqual((VM_SUPERSIZED,
                          {
                              'url': url,
                              'is_eligible': False,
                              'expires': time1,
                              'extended_expiration': time2
                          },
                          self.instance.id),
                         get_vm_state(self.user, self.desktop_type))
