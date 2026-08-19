from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import novaclient

from django.conf import settings

from vm_manager.constants import ACTIVE, SHUTDOWN, RESCUE, \
    NO_VM, VM_ERROR, VM_SHELVED, VM_WAITING
from vm_manager.models import VMStatus, Instance, Volume, Expiration, \
    EXP_EXPIRY_FAILED_RETRYABLE, EXP_EXPIRY_COMPLETED
from vm_manager.tests.fakes import FakeNectar, FakeServer
from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase
from vm_manager.utils.cleanup import cleanup_stuck_terminations

utc = timezone.utc


class CleanupStuckTerminationsTests(VMFunctionTestBase):

    def _mark_stuck(self, instance, volume=None, age=None):
        if age is None:
            age = settings.TERMINATION_CLEANUP_AGE + 60
        marked = datetime.now(utc) - timedelta(seconds=age)
        instance.marked_for_deletion = marked
        instance.save()
        if volume:
            volume.marked_for_deletion = marked
            volume.save()

    @patch('vm_manager.utils.cleanup.get_nectar')
    def test_cleanup_nothing_stuck(self, mock_get_nectar):
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get = Mock()

        # A live desktop, and a delete still within the cleanup age.
        self.build_fake_vol_inst_status(ip_address='10.0.0.99')
        _, fake_instance, _ = self.build_fake_vol_inst_status(
            instance_id='e5b8a900-f3f6-442f-8382-4b2b7f183e0a',
            volume_id='c8506202-6b39-11f0-9721-fb1a09cd7a3b',
            ip_address='10.0.0.100', status=NO_VM)
        self._mark_stuck(fake_instance, age=60)

        counts = cleanup_stuck_terminations()

        self.assertEqual(0, counts['checked'])
        fake_nectar.nova.servers.get.assert_not_called()

    @patch('vm_manager.utils.cleanup.get_nectar')
    def test_cleanup_completes_shelve(self, mock_get_nectar):
        # The shelve workflow errored, but Nova finished the delete
        # later: the cleanup records the shelve.
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(code=42)

        fake_volume, fake_instance, fake_vm_status = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_ERROR)
        self._mark_stuck(fake_instance)
        fake_instance.error(
            "ran out of retries trying to terminate shelved instance")

        counts = cleanup_stuck_terminations()

        self.assertEqual(1, counts['checked'])
        self.assertEqual(1, counts['completed'])
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.deleted)
        self.assertIsNone(instance.error_flag)
        self.assertIsNone(instance.error_message)
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNotNone(volume.shelved_at)
        self.assertIsNotNone(volume.expiration)
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_SHELVED, vm_status.status)
        self.assertEqual(100, vm_status.status_progress)

    @patch('vm_manager.utils.cleanup.get_nectar')
    def test_cleanup_completes_expired_shelve(self, mock_get_nectar):
        # An expiry-driven shelve that failed retryably is marked
        # completed once the cleanup finishes it.
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(code=42)

        fake_volume, fake_instance, fake_vm_status = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_ERROR)
        fake_instance.set_expires(datetime.now(utc) - timedelta(days=1),
                                  stage=EXP_EXPIRY_FAILED_RETRYABLE)
        self._mark_stuck(fake_instance)

        counts = cleanup_stuck_terminations()

        self.assertEqual(1, counts['completed'])
        instance = Instance.objects.get(pk=fake_instance.pk)
        expiration = Expiration.objects.get(pk=instance.expiration.pk)
        self.assertEqual(EXP_EXPIRY_COMPLETED, expiration.stage)

    @patch('vm_manager.utils.cleanup.get_nectar')
    def test_cleanup_completes_delete(self, mock_get_nectar):
        # The delete workflow errored: the instance is recorded as
        # deleted, but the volume is left for the admin actions.
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(code=42)

        fake_volume, fake_instance, fake_vm_status = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=NO_VM)
        self._mark_stuck(fake_instance, volume=fake_volume)
        fake_instance.error("Ran out of retries trying to delete")

        counts = cleanup_stuck_terminations()

        self.assertEqual(1, counts['completed'])
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.deleted)
        self.assertIsNone(instance.error_flag)
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNone(volume.shelved_at)
        self.assertIsNone(volume.deleted)
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(NO_VM, vm_status.status)

    @patch('vm_manager.utils.cleanup.get_nectar')
    def test_cleanup_redeletes_shutoff(self, mock_get_nectar):
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.delete = Mock()

        fake_volume, fake_instance, fake_vm_status = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_ERROR)
        self._mark_stuck(fake_instance)
        fake_nectar.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=SHUTDOWN)

        counts = cleanup_stuck_terminations()

        self.assertEqual(1, counts['deleted'])
        fake_nectar.nova.servers.delete.assert_called_once_with(
            fake_instance.id)
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNone(instance.deleted)
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNone(volume.shelved_at)

    @patch('vm_manager.utils.cleanup.get_nectar')
    def test_cleanup_stops_active(self, mock_get_nectar):
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.stop = Mock()
        fake_nectar.nova.servers.delete = Mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99', status=VM_WAITING)
        self._mark_stuck(fake_instance)
        fake_nectar.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=ACTIVE)

        counts = cleanup_stuck_terminations()

        self.assertEqual(1, counts['stopped'])
        fake_nectar.nova.servers.stop.assert_called_once_with(
            fake_instance.id)
        fake_nectar.nova.servers.delete.assert_not_called()

    @patch('vm_manager.utils.cleanup.get_nectar')
    def test_cleanup_skips_unexpected_state(self, mock_get_nectar):
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.stop = Mock()
        fake_nectar.nova.servers.delete = Mock()

        _, fake_instance, fake_vm_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99', status=VM_ERROR)
        self._mark_stuck(fake_instance)
        fake_nectar.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=RESCUE)

        counts = cleanup_stuck_terminations()

        self.assertEqual(1, counts['skipped'])
        fake_nectar.nova.servers.stop.assert_not_called()
        fake_nectar.nova.servers.delete.assert_not_called()
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNone(instance.deleted)

    @patch('vm_manager.utils.cleanup.get_nectar')
    def test_cleanup_dry_run(self, mock_get_nectar):
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get = Mock()
        fake_nectar.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(code=42)

        fake_volume, fake_instance, fake_vm_status = \
            self.build_fake_vol_inst_status(
                ip_address='10.0.0.99', status=VM_ERROR)
        self._mark_stuck(fake_instance)

        counts = cleanup_stuck_terminations(dry_run=True)

        self.assertEqual(1, counts['completed'])
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNone(instance.deleted)
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNone(volume.shelved_at)
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(VM_ERROR, vm_status.status)
