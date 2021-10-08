import pdb

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
from vm_manager.constants import ERROR, VM_OKAY, VM_DELETED, VM_WAITING, \
    VM_CREATING, NO_VM, LAUNCH_WAIT_SECONDS
from vm_manager.models import VMStatus
from vm_manager.utils.utils import get_nectar, after_time
from vm_manager.views import launch_vm_worker, delete_vm_worker

from vm_manager.views import launch_vm, delete_vm


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
        self.assertEqual(f"A VMStatus for {self.user} and "
                         f"{self.desktop_type.id} already exists",
                         launch_vm(self.user, self.desktop_type))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_launch_vm(self, mock_rq):
        self.build_existing_vm(VM_DELETED)

        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue
        now = datetime.now(timezone.utc)

        self.assertEqual(f"Status of [feature][desktop][{self.user}] "
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
    def test_delete_vm_nonexistent(self, mock_rq):
        with self.assertRaises(Http404):
            delete_vm(self.user, uuid.uuid4(), self.feature)

        self.build_existing_vm(None)
        self.assertEqual(f"No VMStatus found when trying to user delete "
                         f"Instance {self.instance.id}",
                         delete_vm(self.user, self.instance.id, self.feature))

        self.build_existing_vm(NO_VM)
        self.assertEqual(f"VMStatus has wrong status ({NO_VM}) when trying "
                         f"to user delete Instance {self.instance.id}",
                         delete_vm(self.user, self.instance.id, self.feature))

        self.build_existing_vm(VM_DELETED)
        self.assertEqual(f"VMStatus has wrong status ({VM_DELETED}) when "
                         f"trying to user delete Instance {self.instance.id}",
                         delete_vm(self.user, self.instance.id, self.feature))

        mock_rq.get_queue.assert_not_called()

    @patch('vm_manager.views.django_rq')
    def test_delete_vm(self, mock_rq):
        mock_queue = Mock()
        mock_rq.get_queue.return_value = mock_queue

        self.build_existing_vm(VM_OKAY)
        self.assertEqual(f"Status of [{self.feature}][{self.desktop_type.id}]"
                         f"[{self.user}] is {NO_VM}",
                         delete_vm(self.user, self.instance.id, self.feature))

        vm_status = VMStatus.objects.get(pk=self.vm_status.pk)
        self.assertEqual(VM_DELETED, vm_status.status)
        self.assertIsNotNone(vm_status.instance.marked_for_deletion)
        self.assertIsNotNone(vm_status.instance.boot_volume.marked_for_deletion)

        mock_rq.get_queue.assert_called_once_with("default")
        mock_queue.enqueue.assert_called_once_with(
            delete_vm_worker, self.instance)
