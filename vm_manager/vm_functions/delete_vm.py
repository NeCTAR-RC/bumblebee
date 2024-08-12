from datetime import datetime, timedelta, timezone
import logging

import cinderclient
import django_rq
import novaclient

from django.conf import settings

from vm_manager.constants import ACTIVE, SHUTDOWN, NO_VM, VM_SHELVED, \
    VOLUME_AVAILABLE, BACKUP_CREATING, BACKUP_AVAILABLE, VM_WAITING, \
    WF_RETRY, WF_SUCCESS, WF_FAIL, WF_CONTINUE
from vm_manager.models import VMStatus, Expiration, \
    EXP_EXPIRING, EXP_EXPIRY_COMPLETED, \
    EXP_EXPIRY_FAILED, EXP_EXPIRY_FAILED_RETRYABLE
from vm_manager.utils.utils import get_nectar, after_time

from guacamole.models import GuacamoleConnection


logger = logging.getLogger(__name__)

utc = timezone.utc

# Combine the delete and archive workflows into one module because they
# are too difficult to separate.  (I tried a dynamic import, but it made
# it too hard to implement proper unit tests.)


def delete_vm_worker(instance, archive=False):
    logger.info(f"About to delete {instance}")

    if instance.guac_connection:
        GuacamoleConnection.objects.filter(instance=instance).delete()
        instance.guac_connection = None
        instance.save()

    n = get_nectar()
    try:
        status = n.nova.servers.get(instance.id).status
        if status == ACTIVE:
            n.nova.servers.stop(instance.id)
        elif status == SHUTDOWN:
            logger.info(f"{instance} already shutdown in Nova.")
        else:
            # Possible states include stuck while resizing, paused / locked
            # due to security incident, ERROR cause by stuck launching (?)
            logger.error(f"Nova instance for {instance} is in unexpected "
                         f"state {status}.  Needs manual cleanup.")
            instance.error(f"Nova instance state is {status}")
            return WF_RETRY

    except novaclient.exceptions.NotFound:
        logger.error(f"Trying to delete {instance} but it is not "
                     "found in Nova.")
        # It no longer matters, but record the fact that the Nova instance
        # went missing anyway.
        instance.error("Nova instance is missing", gone=True)

    # Next step is to check if the Instance is Shutoff in Nova before
    # telling Nova to delete it
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(
        timedelta(seconds=settings.INSTANCE_POLL_SHUTOFF_WAIT),
        _check_instance_is_shutoff_and_delete, instance,
        settings.INSTANCE_POLL_SHUTOFF_RETRIES,
        _dispose_volume_once_instance_is_deleted,
        (instance, archive, settings.INSTANCE_POLL_DELETED_RETRIES))
    return WF_CONTINUE


def _check_instance_is_shutoff_and_delete(
        instance, retries, func, func_args):
    logger.info(f"Checking whether {instance} is ShutOff.")
    scheduler = django_rq.get_scheduler('default')
    if not instance.check_shutdown_status() and retries > 0:
        # If the instance is not Shutoff, schedule the recheck
        logger.info(f"{instance} is not yet SHUTOFF! Will check again "
                    f"in {settings.INSTANCE_POLL_SHUTOFF_WAIT} seconds with "
                    f"{retries} retries remaining.")
        scheduler.enqueue_in(
            timedelta(seconds=settings.INSTANCE_POLL_SHUTOFF_WAIT),
            _check_instance_is_shutoff_and_delete, instance,
            retries - 1, func, func_args)
        return WF_CONTINUE
    if retries <= 0:
        logger.info(f"Ran out of retries shutting down {instance}. "
                    "Proceeding to delete Nova instance anyway!")

    # Update status if something is waiting
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, instance.boot_volume.requesting_feature, allow_missing=True)
    if vm_status and vm_status.status == VM_WAITING:
        vm_status.status_progress = 45
        vm_status.status_message = 'Instance shelving'
        vm_status.save()

    if not delete_instance(instance):
        return WF_FAIL

    # The 'func' will do the next step; e.g. delete the volume
    # or mark the volume as shelved.
    scheduler.enqueue_in(
        timedelta(seconds=settings.INSTANCE_POLL_DELETED_WAIT),
        func, *func_args)
    return WF_CONTINUE


def delete_instance(instance):
    n = get_nectar()
    try:
        n.nova.servers.delete(instance.id)
        logger.info(f"Instructed Nova to delete {instance}")
    except novaclient.exceptions.NotFound:
        logger.info(f"{instance} already deleted")
    except novaclient.exceptions.ClientException:
        logger.exception(f"Instance deletion call for {instance} failed")
        return False
    instance.marked_for_deletion = datetime.now(utc)
    instance.save()
    return True


def _dispose_volume_once_instance_is_deleted(instance, archive, retries):
    n = get_nectar()
    try:
        os_instance = n.nova.servers.get(instance.id)
        logger.debug(f"Instance delete status is retries: {retries} "
                     f"Nova instance: {os_instance}")
    except novaclient.exceptions.NotFound:
        instance.deleted = datetime.now(utc)
        instance.save()
        volume = instance.boot_volume
        if archive:
            logger.info(f"Instance {instance.id} successfully deleted. "
                        f"Proceeding to archive {volume} now!")
            return archive_volume_worker(
                volume, volume.requesting_feature)
        else:
            logger.info(f"Instance {instance.id} successfully deleted. "
                        f"Proceeding to delete {volume} now!")
            if delete_volume(volume):
                scheduler = django_rq.get_scheduler('default')
                scheduler.enqueue_in(
                    timedelta(seconds=settings.VOLUME_POLL_DELETED_WAIT),
                    _wait_until_volume_is_deleted, volume,
                    settings.VOLUME_POLL_DELETED_RETRIES)
                return WF_CONTINUE
            else:
                return _end_delete(volume, WF_RETRY)
    except novaclient.exceptions.ClientException:
        logger.exception(f"Instance get call for {instance} failed")
        return WF_RETRY

    # Nova still has the instance
    if retries > 0:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(
            timedelta(seconds=settings.INSTANCE_POLL_DELETED_WAIT),
            _dispose_volume_once_instance_is_deleted, instance, archive,
            retries - 1)
        return WF_CONTINUE
    else:
        error_message = "Ran out of retries trying to delete"
        instance.error(error_message)
        logger.error(f"{error_message} {instance}")
        return WF_RETRY


def delete_volume_worker(volume):
    if delete_volume(volume):
        return _wait_until_volume_is_deleted(
            volume, settings.VOLUME_POLL_DELETED_RETRIES)
    else:
        return WF_FAIL


def delete_volume(volume):
    n = get_nectar()
    try:
        n.cinder.volumes.delete(volume.id)
    except cinderclient.exceptions.NotFound:
        logger.info(f"Cinder volume missing for {volume}.  Can't delete it.")
    except cinderclient.exceptions.ClientException:
        logger.exception(f"Cinder volume delete failed for {volume}")
        return False

    volume.deleted = datetime.now(utc)
    volume.save()
    return True


def _wait_until_volume_is_deleted(volume, retries):
    n = get_nectar()
    try:
        os_volume = n.cinder.volumes.get(volume.id)
    except cinderclient.exceptions.NotFound:
        logger.info(f"Cinder volume deletion completed for {volume}")
        volume.deleted = datetime.now(utc)
        volume.save()
        return _end_delete(volume, WF_SUCCESS)
    except cinderclient.exceptions.ClientException:
        logger.exception(f"Volume get call for {volume} failed")
        return _end_delete(volume, WF_RETRY)

    if os_volume.status != "deleting":
        logger.error(f"Cinder volume delete failed for {volume}: "
                     f"status is {os_volume.status}")
        return _end_delete(volume, WF_RETRY)

    if retries > 0:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(
            timedelta(seconds=settings.VOLUME_POLL_DELETED_WAIT),
            _wait_until_volume_is_deleted, volume, retries - 1)
        return WF_CONTINUE
    else:
        error_message = "Ran out of retries trying to delete"
        volume.error(error_message)
        logger.error(f"{error_message} {volume}")
        return _end_delete(volume, WF_RETRY)


def delete_backup_worker(volume):
    if not volume.backup_id:
        logger.info(f"No backup to delete for {volume}")
        return WF_SUCCESS
    n = get_nectar()
    try:
        n.cinder.backups.delete(volume.backup_id)
        logger.info(f"Cinder backup delete requested for {volume}, "
                    f"backup {volume.backup_id}")
    except cinderclient.exceptions.NotFound:
        logger.info(f"Cinder backup already deleted for {volume}, "
                    f"backup {volume.backup_id}")
        volume.backup_id = None
        volume.save()
        return WF_SUCCESS
    except cinderclient.exceptions.ClientException:
        logger.exception(f"Cinder backup delete failed for {volume}, "
                         f"backup {volume.backup_id}")
        return WF_RETRY

    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(
        timedelta(seconds=settings.BACKUP_POLL_DELETED_WAIT),
        _wait_until_backup_is_deleted, volume,
        settings.BACKUP_POLL_DELETED_RETRIES)
    return WF_CONTINUE


def _wait_until_backup_is_deleted(volume, retries):
    n = get_nectar()
    try:
        n.cinder.backups.get(volume.backup_id)
    except cinderclient.exceptions.NotFound:
        logger.info(f"Cinder backup for {volume} has been deleted, "
                    f"backup {volume.backup_id}")
        volume.backup_id = None
        volume.save()
        return _end_delete(volume, WF_SUCCESS)
    except cinderclient.exceptions.ClientException:
        logger.exception(f"Cinder backup get failed for {volume}, "
                         f"backup {volume.backup_id}")
        return _end_delete(volume, WF_RETRY)

    if retries > 0:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(
            timedelta(seconds=settings.BACKUP_POLL_DELETED_WAIT),
            _wait_until_backup_is_deleted, volume,
            retries - 1)
        return WF_CONTINUE
    else:
        logger.info("Cinder backup deletion took too long for {volume}, "
                    f"backup {volume.backup_id}")
        return _end_delete(volume, WF_RETRY)


def _end_delete(volume, wf_status):
    for expiration in [volume.expiration, volume.backup_expiration]:
        if not expiration:
            continue
        expiration = Expiration.objects.get(pk=expiration.pk)
        if expiration.stage == EXP_EXPIRING:
            if wf_status == WF_FAIL:
                expiration.stage = EXP_EXPIRY_FAILED
            elif wf_status == WF_RETRY:
                expiration.stage = EXP_EXPIRY_FAILED_RETRYABLE
            elif wf_status == WF_SUCCESS:
                expiration.stage = EXP_EXPIRY_COMPLETED
            expiration.stage_date = datetime.now(utc)
            expiration.save()
    return wf_status


def archive_volume_worker(volume, requesting_feature):
    "Archive a volume by creating a Cinder backup then deleting the volume."

    # This "hides" the volume from the get_volume method allowing
    # another one to be created / launched without errors.
    volume.marked_for_deletion = datetime.now(utc)
    volume.save()

    n = get_nectar()
    try:
        cinder_volume = n.cinder.volumes.get(volume_id=volume.id)
        if cinder_volume.status != VOLUME_AVAILABLE:
            logger.error(
                "Cannot archive volume with Cinder status "
                f"{cinder_volume.status}: {volume}. Manual cleanup needed.")
            return _end_delete(volume, WF_RETRY)
    except cinderclient.exceptions.NotFound:
        volume.error("Cinder volume missing.  Cannot be archived.")
        logger.error(
            f"Cinder volume missing for {volume}. Cannot be archived.")
        return _end_delete(volume, WF_SUCCESS)

    try:
        backup = n.cinder.backups.create(
            volume.id, name=f"{volume.id}-archive")
        logger.info(
            f'Cinder backup {backup.id} started for volume {volume.id}')
    except cinderclient.exceptions.ClientException as e:
        volume.error("Cinder backup failed")
        logger.error(
            f"Cinder backup failed for volume {volume.id}: {e}")
        return _end_delete(volume, WF_RETRY)

    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=5), wait_for_backup,
                         volume, backup.id,
                         after_time(settings.ARCHIVE_WAIT))

    # This allows the user to launch a new desktop immediately.
    vm_status = VMStatus.objects.get_vm_status_by_volume(
        volume, requesting_feature, allow_missing=True)
    if vm_status:
        vm_status.status = NO_VM
        vm_status.save()

    return WF_CONTINUE


def wait_for_backup(volume, backup_id, deadline):
    n = get_nectar()
    try:
        details = n.cinder.backups.get(backup_id)
    except cinderclient.exceptions.NotFound:
        # The backup has disappeared ...
        logger.error(f"Backup {backup_id} for volume {volume} not "
                     "found.  Presumed failed.")
        return _end_delete(volume, WF_RETRY)

    if details.status == BACKUP_CREATING:
        if datetime.now(utc) > deadline:
            logger.error(f"Backup took too long: backup {backup_id}, "
                         f"volume {volume}")
            return _end_delete(volume, WF_RETRY)
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(timedelta(seconds=settings.ARCHIVE_POLL_WAIT),
                             wait_for_backup, volume, backup_id, deadline)
        return WF_CONTINUE
    elif details.status == BACKUP_AVAILABLE:
        logger.info(f"Backup {backup_id} completed for volume {volume}")
        volume.backup_id = backup_id
        volume.archived_at = datetime.now(utc)
        volume.save()
        volume.set_backup_expires(
            datetime.now(utc) + timedelta(days=settings.BACKUP_LIFETIME))
        logger.info(f"About to delete the archived volume {volume}")
        delete_volume(volume)
        return _end_delete(volume, WF_SUCCESS)
    else:
        logger.error(f"Backup {backup_id} for volume {volume} is in "
                     f"unexpected state {details.status}")
        return _end_delete(volume, WF_FAIL)


def archive_expired_volume(volume, requesting_feature):
    try:
        vm_status = VMStatus.objects.get_vm_status_by_volume(
            volume, requesting_feature)
        if vm_status.status != VM_SHELVED:
            logger.error(f"Declined to archive {volume} with "
                         f"unexpected vmstatus state: {vm_status.status}")
            return WF_FAIL
        else:
            return archive_volume_worker(volume, requesting_feature)
    except Exception:
        # FIX ME - this isn't right ...
        logger.exception(f"Cannot retrieve vm_status for {volume}")
    return WF_FAIL
