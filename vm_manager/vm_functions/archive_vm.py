import django_rq
import logging

from datetime import datetime, timedelta
from django.conf import settings
from django.utils.timezone import utc

from vm_manager.constants import VM_SHELVED, VM_WAITING, NO_VM, \
    VOLUME_AVAILABLE, BACKUP_CREATING, BACKUP_AVAILABLE, \
    ARCHIVE_WAIT_SECONDS, ARCHIVE_POLL_SECONDS
from vm_manager.models import Volume, VMStatus
from vm_manager.vm_functions.delete_vm import delete_volume
from vm_manager.utils.utils import get_nectar, after_time

from guacamole.models import GuacamoleConnection

logger = logging.getLogger(__name__)


def archive_vm_worker(volume, requesting_feature):
    # This "hides" the volume from the get_volume method allowing
    # another one to be created / launched without errors.
    volume.marked_for_deletion = datetime.now(utc)
    volume.save()

    n = get_nectar()
    openstack_volume = n.cinder.volumes.get(volume_id=volume.id)
    if openstack_volume.status != VOLUME_AVAILABLE:
        msg = (f"Cannot archive a volume with status "
               f"{openstack_volume.status}: {volume}")
        logger.error(msg)
        raise RuntimeWarning(msg)

    backup = n.cinder.backups.create(
        volume.id, name=f"{volume.id}-archive")
    logger.info(f'Cinder backup {backup.id} started for volume {volume.id}')

    # Free up the user's slot to allow them to launch a new desktop
    # immediately.  As far as they are concerned the old one is "gone".
    vm_status = VMStatus.objects.get_vm_status_by_volume(
        volume, requesting_feature)
    vm_status.status = NO_VM
    vm_status.save()

    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=5), wait_for_backup,
                         volume, backup.id, after_time(ARCHIVE_WAIT_SECONDS))


def wait_for_backup(volume, backup_id, deadline):
    n = get_nectar()
    details = n.cinder.backups.get(backup_id)
    if details.status == BACKUP_CREATING:
        if datetime.now(utc) > deadline:
            logger.error(f"Backup took too long: backup {backup_id}, "
                         f"volume {volume}")
            return
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(timedelta(seconds=ARCHIVE_POLL_SECONDS),
                             wait_for_backup, volume, backup_id, deadline)
    elif details.status == BACKUP_AVAILABLE:
        logger.info(f"Backup {backup_id} completed for volume {volume}")
        volume.backup_id = backup_id
        volume.archived_at = datetime.now(utc)
        volume.save()
        logger.info(f"About to delete the archived volume {volume}")
        delete_volume(volume)
    else:
        logger.error(f"Backup {backup_id} for volume {volume} is in "
                     f"unexpected state {details.status}")


def archive_expired_vm(volume, requesting_feature, dry_run=False):
    try:
        vm_status = VMStatus.objects.get_vm_status_by_volume(
            volume, requesting_feature)
        if vm_status.status != VM_SHELVED:
            logger.info(f"Skipping archiving of {volume} "
                        f"in unexpected state: {vm_status}")
        elif not dry_run:
            archive_vm_worker(volume, requesting_feature)
            return True
    except Exception:
        logger.exception(f"Cannot retrieve vm_status for {volume}")
    return False
