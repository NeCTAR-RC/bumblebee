import copy
from datetime import datetime, timedelta
from uuid import uuid4

import novaclient

from unittest.mock import Mock, patch, call

from django.conf import settings
from django.test import TestCase
from django.utils.timezone import utc

from researcher_desktop.utils.utils import get_desktop_type, desktops_feature
from guacamole.tests.factories import GuacamoleConnectionFactory
from vm_manager.tests.common import UUID_1, UUID_2, UUID_3, UUID_4
from vm_manager.tests.fakes import Fake, FakeServer, FakeVolume, FakeNectar
from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase

from vm_manager.constants import ACTIVE, SHUTDOWN, \
    VM_MISSING, VM_OKAY, VM_SHELVED, VM_WAITING, NO_VM, \
    ARCHIVE_POLL_SECONDS, ARCHIVE_WAIT_SECONDS, \
    BACKUP_CREATING, BACKUP_AVAILABLE
from vm_manager.models import VMStatus, Volume, Instance
from vm_manager.vm_functions.archive_vm import archive_vm_worker, \
    wait_for_backup
from vm_manager.utils.utils import get_nectar


class ArchiveVMTests(VMFunctionTestBase):

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.archive_vm.django_rq')
    @patch('vm_manager.vm_functions.archive_vm.logger')
    @patch('vm_manager.utils.utils.datetime')
    def test_archive_vm_worker(self, mock_datetime, mock_logger, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_volume, _, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_SHELVED)
        backup_id = uuid4()
        now = datetime.now(utc)
        mock_datetime.now.return_value = now

        fake_nectar = get_nectar()
        fake_nectar.cinder.volumes.get.return_value = Fake(status='sleeping')

        with self.assertRaises(RuntimeWarning) as cm:
            archive_vm_worker(fake_volume, self.FEATURE)
        self.assertEqual(f"Cannot archive a volume with status sleeping: "
                         f"{fake_volume}",
                         str(cm.exception))
        fake_nectar.cinder.volumes.get.assert_called_once_with(
            volume_id=fake_volume.id)

        fake_nectar.cinder.volumes.get.return_value = Fake(status='available')
        fake_nectar.cinder.volumes.get.reset_mock()
        fake_nectar.cinder.backups.create.return_value = Fake(id=backup_id)
        archive_vm_worker(fake_volume, self.FEATURE)
        vm_status = VMStatus.objects.get(pk=fake_vm_status.pk)
        self.assertEqual(NO_VM, vm_status.status)

        fake_nectar.cinder.backups.create.assert_called_once_with(
            fake_volume.id, name=f"{fake_volume.id}-archive")

        mock_datetime.now.assert_called_once()
        mock_logger.info.assert_called_once_with(
            f'Cinder backup {backup_id} started for volume {fake_volume.id}')

        mock_rq.get_scheduler.assert_called_once_with("default")
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=5), wait_for_backup, fake_volume, backup_id,
            now + timedelta(seconds=ARCHIVE_WAIT_SECONDS))

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.archive_vm.django_rq')
    @patch('vm_manager.vm_functions.archive_vm.logger')
    @patch('vm_manager.vm_functions.archive_vm.delete_volume')
    def test_wait_for_backup(self, mock_delete, mock_logger, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        fake_volume, _, fake_vm_status = self.build_fake_vol_inst_status(
            status=VM_SHELVED)
        backup_id = uuid4()

        fake_nectar = get_nectar()
        fake_nectar.cinder.backups.get.return_value = Fake(
            status=BACKUP_CREATING, id=backup_id)

        deadline = datetime.now(utc) - timedelta(seconds=10)
        wait_for_backup(fake_volume, backup_id, deadline)
        fake_nectar.cinder.backups.get.assert_called_once_with(backup_id)
        mock_logger.error.assert_called_once_with(
            f'Backup took too long: backup {backup_id}, volume {fake_volume}')
        mock_rq.get_scheduler.assert_not_called()

        deadline = datetime.now(utc) + timedelta(seconds=10)
        fake_nectar.cinder.backups.get.reset_mock()
        mock_logger.error.reset_mock()
        wait_for_backup(fake_volume, backup_id, deadline)
        fake_nectar.cinder.backups.get.assert_called_once_with(backup_id)
        mock_logger.error.assert_not_called()
        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=ARCHIVE_POLL_SECONDS), wait_for_backup,
            fake_volume, backup_id, deadline)

        mock_logger.info.reset_mock()
        mock_rq.get_scheduler.reset_mock()
        fake_nectar.cinder.backups.get.reset_mock()
        fake_nectar.cinder.backups.get.return_value = Fake(
            status=BACKUP_AVAILABLE, id=backup_id)

        wait_for_backup(fake_volume, backup_id, deadline)
        fake_nectar.cinder.backups.get.assert_called_once_with(backup_id)
        mock_logger.error.assert_not_called()
        mock_logger.info.assert_has_calls([
            call(f'Backup {backup_id} completed for volume {fake_volume}'),
            call(f'About to delete the archived volume {fake_volume}')])
        mock_rq.get_scheduler.assert_not_called()
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertEqual(backup_id, volume.backup_id)
        self.assertIsNotNone(volume.archived_at)
        mock_delete.assert_called_once_with(fake_volume)

        mock_logger.info.reset_mock()
        mock_rq.get_scheduler.reset_mock()
        fake_nectar.cinder.backups.get.reset_mock()
        fake_nectar.cinder.backups.get.return_value = Fake(
            status="reversing", id=backup_id)

        wait_for_backup(fake_volume, backup_id, deadline)
        fake_nectar.cinder.backups.get.assert_called_once_with(backup_id)
        mock_logger.error.assert_called_once_with(
            f'Backup {backup_id} for volume {fake_volume} '
            f'is in unexpected state reversing')
