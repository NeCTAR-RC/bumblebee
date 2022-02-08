import uuid
import copy
from datetime import datetime, timedelta

from unittest.mock import Mock, patch, call

from django.http import Http404, HttpResponseRedirect
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils.timezone import utc

from researcher_workspace.tests.factories import FeatureFactory, UserFactory
from researcher_desktop.tests.factories import DesktopTypeFactory, \
    AvailabilityZoneFactory
from vm_manager.tests.factories import InstanceFactory, VolumeFactory, \
    ResizeFactory, VMStatusFactory
from vm_manager.tests.fakes import Fake, FakeNectar

from vm_manager.constants import ERROR, ACTIVE, SHUTDOWN, VERIFY_RESIZE, \
    BUILD, REBUILD, RESIZE, REBOOT, RESCUE, REBOOT_HARD, REBOOT_SOFT, \
    VM_OKAY, VM_DELETED, VM_WAITING, \
    VM_CREATING, VM_RESIZING, NO_VM, VM_SHELVED, VM_MISSING, VM_ERROR, \
    VM_SHUTDOWN, VM_SUPERSIZED, ALL_VM_STATES, LAUNCH_WAIT_SECONDS, \
    CLOUD_INIT_STARTED, CLOUD_INIT_FINISHED, SCRIPT_OKAY, \
    EXTEND_BUTTON, EXTEND_BOOST_BUTTON, BOOST_BUTTON

from vm_manager.models import VMStatus, Instance, Volume
from vm_manager.utils.utils import get_nectar, after_time
from vm_manager.views import launch_vm_worker, delete_vm_worker, \
    shelve_vm_worker, unshelve_vm_worker, reboot_vm_worker, \
    supersize_vm_worker, downsize_vm_worker

from vm_manager.views import launch_vm, delete_vm, shelve_vm, unshelve_vm, \
    reboot_vm, supersize_vm, downsize_vm, get_vm_state, render_vm, notify_vm, \
    phone_home, rd_report_for_user, admin_delete_vm


class VMManagerViewTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()
        self.feature = FeatureFactory.create(name='feature',
                                             app_name='feature_app')
        self.desktop_type = DesktopTypeFactory.create(name='some desktop',
                                                      id='desktop',
                                                      feature=self.feature)
        self.zone = AvailabilityZoneFactory.create(name="a_zone",
                                                   zone_weight=1)

    def build_existing_vm(self, status, expires=None):
        self.volume = VolumeFactory.create(
            id=uuid.uuid4(), user=self.user,
            operating_system=self.desktop_type.id,
            requesting_feature=self.feature,
            zone=self.zone.name)
        self.instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=self.volume,
            ip_address='10.0.0.1', expires=expires)
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
            f"User {self.user} already has 1 live desktops",
            launch_vm(self.user, self.desktop_type, self.zone))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_launch_vm(self, mock_rq):
        self.build_existing_vm(VM_DELETED)

        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        now = datetime.now(utc)

        self.assertEqual(
            f"Status of desktop for {self.user} "
            f"is {VM_WAITING}",
            launch_vm(self.user, self.desktop_type, self.zone))
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.desktop_type)
        self.assertTrue(vm_status != self.vm_status)
        self.assertEqual(VM_CREATING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
        self.assertEqual(self.desktop_type.id, vm_status.operating_system)
        self.assertEqual(self.feature, vm_status.requesting_feature)
        self.assertTrue(now <= vm_status.created)
        self.assertTrue(after_time(LAUNCH_WAIT_SECONDS)
                        >= vm_status.wait_time)

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            launch_vm_worker, user=self.user, desktop_type=self.desktop_type,
            zone=self.zone)

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
            f"Status of {self.desktop_type.id} for "
            f"{self.user} is {NO_VM}",
            delete_vm(self.user, self.instance.id, self.feature))

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
            f"Status of {self.desktop_type.id} for {self.user} "
            f"is {VM_WAITING}",
            shelve_vm(self.user, self.instance.id, self.feature))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            shelve_vm_worker, self.instance, self.feature)
        vm_status = VMStatus.objects.get(pk=self.vm_status.id)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
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
            f"Status of {self.desktop_type.id} for {self.user} "
            f"is {VM_CREATING}",
            unshelve_vm(self.user, self.desktop_type))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            unshelve_vm_worker, user=self.user, desktop_type=self.desktop_type,
            zone=self.zone)
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.desktop_type)
        self.assertTrue(vm_status.pk != self.vm_status.pk)
        self.assertEqual(VM_CREATING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
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
                reboot_vm(self.user, self.instance.id,
                          REBOOT_SOFT, self.feature))

        self.build_existing_vm(VM_OKAY)
        with self.assertRaises(Http404):
            reboot_vm(self.user, self.instance.id, "squirrelly", self.feature)

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_reboot_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        self.build_existing_vm(VM_OKAY)
        now = datetime.now(utc)

        self.assertEqual(
            f"Status of {self.desktop_type.id} for "
            f"{self.user} is {VM_WAITING}",
            reboot_vm(self.user, self.instance.id, REBOOT_SOFT, self.feature))

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            reboot_vm_worker, self.user, self.instance.id, REBOOT_SOFT,
            VM_OKAY, self.feature)
        vm_status = VMStatus.objects.get_latest_vm_status(
            self.user, self.desktop_type)
        self.assertEqual(vm_status.pk, self.vm_status.pk)
        self.assertEqual(VM_WAITING, vm_status.status)
        self.assertEqual(0, vm_status.status_progress)
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
        now = datetime.now(utc)

        self.assertEqual(
            f"Status of {self.desktop_type.id} for {self.user} "
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
        self.assertEqual(0, vm_status.status_progress)
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
        now = datetime.now(utc)

        self.assertEqual(
            f"Status of {self.desktop_type.id} for {self.user} "
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
        self.assertEqual(0, vm_status.status_progress)
        self.assertTrue(now < vm_status.wait_time)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    def test_get_vm_state(self):
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
            instance=self.instance, wait_time=datetime.now(utc))
        self.assertEqual((VM_ERROR, "Instance Not Ready", self.instance.id),
                         get_vm_state(self.user, self.desktop_type))

        vm_status = VMStatusFactory.create(
            status=VM_WAITING, user=self.user,
            operating_system=self.desktop_type.id,
            requesting_feature=self.feature,
            wait_time=datetime.now(utc))
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
                           'expires': date1,
                           'extended_expiration': date2
                          },
                          self.instance.id),
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
        resize = ResizeFactory.create(instance=self.instance, expires=date1)

        res = get_vm_state(self.user, self.desktop_type)

        self.assertEqual(
            (VM_SUPERSIZED,
             {'url': url,
              'extension': timedelta(days=2),
              'expires': date1,
              'extended_expiration': date2
             },
             self.instance.id),
            get_vm_state(self.user, self.desktop_type))

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
        date1 = now + timedelta(days=settings.BOOST_EXPIRY)
        date2 = now + timedelta(days=settings.BOOST_EXPIRY)

        mock_policy.permitted_extension.return_value = \
            timedelta(days=settings.BOOST_EXPIRY)
        mock_policy.new_expiry.return_value = \
            now + timedelta(days=settings.BOOST_EXPIRY)

        request = "The Request"
        buttons = ["ONE", "TWO", EXTEND_BUTTON,
                   EXTEND_BOOST_BUTTON, BOOST_BUTTON]

        self.build_existing_vm(VM_OKAY, expires=date1)
        self.assertEqual(("rendered", "rendered", VM_OKAY),
                         render_vm(request, self.user, self.desktop_type,
                                   buttons))
        context = {
            'state': VM_OKAY,
            'what_to_show': {
                'url': url,
                'extension': timedelta(days=settings.BOOST_EXTENSION),
                'expires': date1,
                'extended_expiration': date2},
            'desktop_type': self.desktop_type,
            'vm_id': self.instance.id,
            'buttons_to_display': ['ONE', 'TWO', EXTEND_BUTTON, BOOST_BUTTON],
            'app_name': self.feature.app_name,
            'requesting_feature': self.feature,
            'VM_WAITING': VM_WAITING,
            'vm_status': self.vm_status,
        }
        calls = [call(f"vm_manager/html/{VM_OKAY}.html",
                      context, request),
                 call(f"vm_manager/javascript/{VM_OKAY}.js",
                      context, request)]
        mock_policy.permitted_extension.assert_called_once_with(self.instance)
        mock_policy.new_expiry.assert_called_once_with(self.instance)
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
        date1 = now + timedelta(days=settings.BOOST_EXPIRY)
        date2 = now + timedelta(days=settings.BOOST_EXPIRY)
        resize = ResizeFactory.create(instance=self.instance, expires=date1)

        mock_policy.permitted_extension.return_value = \
            timedelta(days=settings.BOOST_EXPIRY)
        mock_policy.new_expiry.return_value = \
            now + timedelta(days=settings.BOOST_EXPIRY)

        request = "The Request"
        buttons = ["ONE", "TWO", EXTEND_BUTTON,
                   EXTEND_BOOST_BUTTON, BOOST_BUTTON]
        self.assertEqual(("rendered", "rendered", VM_SUPERSIZED),
                         render_vm(request, self.user, self.desktop_type,
                                   buttons))
        context = {
            'state': VM_SUPERSIZED,
            'what_to_show': {
                'url': url,
                'extension': timedelta(days=settings.BOOST_EXTENSION),
                'expires': date1,
                'extended_expiration': date2},
            'desktop_type': self.desktop_type,
            'vm_id': self.instance.id,
            'buttons_to_display': ['ONE', 'TWO', EXTEND_BOOST_BUTTON],
            'app_name': self.feature.app_name,
            'requesting_feature': self.feature,
            'VM_WAITING': VM_WAITING,
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
            f'Your some desktop desktop is set to resize back to the default '
            f'size on {date1}')

        # Reset for supersized (not allowed)
        mock_policy.permitted_extension.reset_mock()
        mock_policy.new_expiry.reset_mock()
        mock_loader.render_to_string.reset_mock()
        mock_messages.info.reset_mock()

        mock_policy.permitted_extension.return_value = timedelta(seconds=0)
        mock_policy.new_expiry.return_value = date1

        self.assertEqual(("rendered", "rendered", VM_SUPERSIZED),
                         render_vm(request, self.user, self.desktop_type,
                                   buttons))
        context['what_to_show'] = {
            'url': url,
            'extension': timedelta(seconds=0),
            'expires': date1,
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
            f'Your some desktop desktop is set to resize back to the default '
            f'size on {date1}')

    @patch('vm_manager.views.logger')
    @patch('vm_manager.views.generate_hostname')
    def test_notify_vm(self, mock_gen, mock_logger):
        fake_request = Fake(GET={
            'ip': '10.0.0.1',
            'hn': 'foo',
            'os': self.desktop_type.id,
            'state': SCRIPT_OKAY,
            'msg': CLOUD_INIT_STARTED
        })
        with self.assertRaises(Http404):
            notify_vm(fake_request, self.feature)
        mock_logger.error.assert_called_with(
            "No current Instance found with IP address 10.0.0.1")

        mock_gen.return_value = "bzzzt"
        self.build_existing_vm(VM_WAITING)
        with self.assertRaises(Http404):
            notify_vm(fake_request, self.feature)
        mock_logger.error.assert_called_with(
            f"Hostname provided in request does not match "
            f"hostname of volume {self.instance}, foo")
        mock_gen.assert_called_with(
            self.volume.hostname_id, self.desktop_type.id)

        mock_gen.reset_mock()
        mock_logger.error.reset_mock()
        mock_gen.return_value = "foo"

        self.assertEqual(
            f"{self.instance.ip_address}, {self.desktop_type.id}, "
            f"{SCRIPT_OKAY}, {CLOUD_INIT_STARTED}",
            notify_vm(fake_request, self.feature))

        mock_gen.assert_called_with(
            self.volume.hostname_id, self.desktop_type.id)
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
            'os': self.desktop_type.id,
            'state': SCRIPT_OKAY,
            'msg': CLOUD_INIT_FINISHED
        })

        self.assertEqual(
            f"{self.instance.ip_address}, {self.desktop_type.id}, "
            f"{SCRIPT_OKAY}, {CLOUD_INIT_FINISHED}",
            notify_vm(fake_request, self.feature))

        mock_gen.assert_called_with(
            self.volume.hostname_id, self.desktop_type.id)
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
            'os': self.desktop_type.id,
            'state': 42,
            'msg': "Other Message"
        })

        self.assertEqual(
            f"{self.instance.ip_address}, {self.desktop_type.id}, "
            f"42, Other Message",
            notify_vm(fake_request, self.feature))

        mock_gen.assert_called_with(
            self.volume.hostname_id, self.desktop_type.id)
        mock_logger.error.assert_called_with(
            f"Notify VM Error: Other Message for instance: "
            f"\"{self.instance}\"")
        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertEqual(VM_ERROR, vm_status.status)
        self.assertEqual("Other Message", vm_status.instance.error_message)

    @patch('vm_manager.views.logger')
    @patch('vm_manager.models.logger')
    @patch('vm_manager.views.generate_hostname')
    def test_phone_home(self, mock_gen, mock_logger_2, mock_logger):
        fake_request = Fake(POST={})
        with self.assertRaises(Http404):
            phone_home(fake_request, self.feature)
        mock_logger.error.assert_called_with("Instance ID not found in data")

        fake_id = uuid.uuid4()
        fake_request = Fake(POST={'instance_id': fake_id})
        with self.assertRaises(Http404):
            phone_home(fake_request, self.feature)
        mock_logger_2.error.assert_called_with(
            f"Trying to get a vm that doesn't exist with vm_id: "
            f"{fake_id}, called by internal")

        self.build_existing_vm(VM_OKAY)
        fake_request = Fake(POST={'instance_id': self.instance.id})
        self.assertEqual(
            f"Unexpected phone home for {self.instance}. "
            f"VM_status is {self.vm_status}",
            phone_home(fake_request, self.feature))

        self.build_existing_vm(VM_WAITING)
        fake_request = Fake(POST={'instance_id': self.instance.id})
        self.assertEqual(
            f"Phone home for {self.instance} successful!",
            phone_home(fake_request, self.feature))
        volume = Volume.objects.get(pk=self.volume.pk)
        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertTrue(volume.ready)
        self.assertEqual(VM_OKAY, vm_status.status)
        self.assertEqual(100, vm_status.status_progress)

        self.build_existing_vm(VM_WAITING)
        resize = ResizeFactory.create(instance=self.instance)
        fake_request = Fake(POST={'instance_id': self.instance.id})
        self.assertEqual(
            f"Phone home for {self.instance} successful!",
            phone_home(fake_request, self.feature))
        volume = Volume.objects.get(pk=self.volume.pk)
        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertTrue(volume.ready)
        self.assertEqual(VM_SUPERSIZED, vm_status.status)
        self.assertEqual(100, vm_status.status_progress)

    @patch('vm_manager.views.datetime')
    def test_rd_report_for_user(self, mock_datetime):
        # Freeze time ...
        now = datetime.now(utc)
        mock_datetime.now.return_value = now

        dt_1 = DesktopTypeFactory.create(
            feature=self.feature, id='dt1', name='desktop one')
        dt_2 = DesktopTypeFactory.create(
            feature=self.feature, id='dt2', name='desktop two')
        dt_ids = ['dt1', 'dt2']
        volume_1 = VolumeFactory.create(
            operating_system=dt_1.id, requesting_feature=self.feature,
            id=uuid.uuid4(), user=self.user)
        volume_2 = VolumeFactory.create(
            operating_system=dt_2.id, requesting_feature=self.feature,
            id=uuid.uuid4(), user=self.user)

        self.assertEqual(
            {
                'user_vm_info': {
                'dt1': [{'count': 0, 'date': now}],
                'dt2': [{'count': 0, 'date': now}]
                }
            },
            rd_report_for_user(self.user, dt_ids, self.feature)
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
            rd_report_for_user(self.user, dt_ids, self.feature))

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
            rd_report_for_user(self.user, dt_ids, self.feature))

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
    @patch('vm_manager.views.django_rq')
    def test_admin_delete_vm(self, mock_rq, mock_logger):
        admin_user = UserFactory.create(username="admin-joe")
        vm_id = uuid.uuid4()

        def fake_build():
            return "redirect"

        def fake_get():
            return "wherever"

        request = Fake(user=AnonymousUser(),
                       get_full_path=fake_get,
                       build_absolute_uri=fake_build)
        res = admin_delete_vm(request, vm_id)
        self.assertEqual(HttpResponseRedirect, res.__class__)
        self.assertEqual(302, res.status_code)
        self.assertEqual("/login/?next=wherever", res.url),

        request = Fake(user=admin_user)
        with self.assertRaises(Http404):
            admin_delete_vm(request, vm_id)
        mock_logger.error.assert_called_once_with(
            f"Attempted admin delete of {vm_id} by "
            f"non-admin user admin-joe")

        admin_user.is_superuser = True
        self.assertEqual(
            f"VMStatus for user admin-joe, feature admin, "
            f"instance {vm_id} is missing. Cannot admin delete VM.",
            admin_delete_vm(request, vm_id))

        mock_rq.get_queue.assert_not_called()
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue

        self.build_existing_vm(VM_OKAY)
        res = admin_delete_vm(request, self.instance.id)
        self.assertEqual(HttpResponseRedirect, res.__class__)
        self.assertEqual(302, res.status_code)
        self.assertEqual(
            f"/rcsadmin/vm_manager/instance/{self.instance.id}/change/",
            res.url),
        mock_logger.info.assert_called_with(
            f"admin-joe admin deleted vm {self.instance.id}")
        mock_rq.get_queue.assert_called_with("default")
        mock_queue.enqueue.assert_called_with(delete_vm_worker, self.instance)
        vms = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertEqual(VM_DELETED, vms.status)
        # No progress updates required ...
        self.assertIsNotNone(vms.instance.marked_for_deletion)
        self.assertIsNotNone(vms.instance.boot_volume.marked_for_deletion)
