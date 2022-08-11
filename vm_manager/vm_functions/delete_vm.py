from datetime import datetime, timedelta
import logging

import cinderclient
import django_rq
import novaclient

from django.utils.timezone import utc

from vm_manager.constants import ACTIVE, SHUTDOWN, NO_VM, VM_SHELVED, \
    VOLUME_AVAILABLE, BACKUP_CREATING, BACKUP_AVAILABLE, VM_WAITING, \
    INSTANCE_DELETION_RETRY_WAIT_TIME, INSTANCE_DELETION_RETRY_COUNT, \
    INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME, \
    INSTANCE_CHECK_SHUTOFF_RETRY_COUNT, \
    ARCHIVE_POLL_SECONDS, ARCHIVE_WAIT_SECONDS
from vm_manager.models import VMStatus
from vm_manager.utils.utils import get_nectar, after_time

from guacamole.models import GuacamoleConnection


logger = logging.getLogger(__name__)

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
            return

    except novaclient.exceptions.NotFound:
        logger.error(f"Trying to delete {instance} but it is not "
                     f"found in Nova.")
        # It no longer matters, but record the fact that the Nova instance
        # went missing anyway.
        instance.error(f"Nova instance is missing")

    # Next step is to check if the Instance is Shutoff in Nova before
    # telling Nova to delete it
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(
        timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
        _check_instance_is_shutoff_and_delete, instance,
        INSTANCE_CHECK_SHUTOFF_RETRY_COUNT,
        _dispose_volume_once_instance_is_deleted,
        (instance, archive, INSTANCE_DELETION_RETRY_COUNT))


def _check_instance_is_shutoff_and_delete(
        instance, retries, func, func_args):
    logger.info(f"Checking whether {instance} is ShutOff.")
    scheduler = django_rq.get_scheduler('default')
    if not instance.check_shutdown_status() and retries > 0:
        # If the instance is not Shutoff, schedule the recheck
        logger.info(f"{instance} is not yet SHUTOFF! Will check again "
                    f"in {INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME} seconds with "
                    f"{retries} retries remaining.")
        scheduler.enqueue_in(
            timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
            _check_instance_is_shutoff_and_delete, instance,
            retries - 1, func, func_args)
        return
    if retries <= 0:
        # TODO - not sure we should delete the instance anyway ...
        logger.info(f"Ran out of retries shutting down {instance}. "
                    f"Proceeding to delete Nova instance anyway!")

    # Update status if something is waiting
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, instance.boot_volume.requesting_feature, allow_missing=True)
    if vm_status and vm_status.status == VM_WAITING:
        vm_status.status_progress = 66
        vm_status.status_message = 'Instance shelving'
        vm_status.save()

    delete_instance(instance)

    # The 'func' will do the next step; e.g. delete the volume
    # or mark the volume as shelved.
    scheduler.enqueue_in(
        timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
        func, *func_args)


def delete_instance(instance):
    n = get_nectar()
    instance.marked_for_deletion = datetime.now(utc)
    instance.save()
    try:
        n.nova.servers.delete(instance.id)
        logger.info(f"Instructed Nova to delete {instance}")
    except novaclient.exceptions.NotFound:
        logger.info(f"{instance} already deleted")
    except Exception as e:
        logger.error(f"Something went wrong with the instance deletion "
                     f"call for {instance}, it raised {e}")


def _dispose_volume_once_instance_is_deleted(instance, archive, retries):
    n = get_nectar()
    try:
        my_instance = n.nova.servers.get(instance.id)
        logger.debug(f"Instance delete status is retries: {retries} "
                     f"Nova instance: {my_instance}")
    except novaclient.exceptions.NotFound:
        instance.deleted = datetime.now(utc)
        instance.save()
        if archive:
            logger.info(f"Instance {instance.id} successfully deleted. "
                        f"Proceeding to archive {instance.boot_volume} now!")
            archive_volume_worker(instance.boot_volume,
                                  instance.boot_volume.requesting_feature)
        else:
            logger.info(f"Instance {instance.id} successfully deleted. "
                        f"Proceeding to delete {instance.boot_volume} now!")
            delete_volume(instance.boot_volume)
        return
    except Exception as e:
        logger.error("something went wrong with the instance get "
                     f"call for {instance}, it raised {e}")
        return

    # Nova still has the instance, and was able to return it to us
    if retries == 0:
        # FIXME ... not sure about this.  Should already have sent the
        # Nova server delete request
        delete_instance(instance)
        scheduler = django_rq.get_scheduler('default')
        # Note in this case I'm using `minutes=` not `seconds=` to give
        # a long wait time that should be sufficient
        scheduler.enqueue_in(
            timedelta(minutes=INSTANCE_DELETION_RETRY_WAIT_TIME),
            _dispose_volume_once_instance_is_deleted, instance, archive,
            retries - 1)
        return

    if retries <= 0:
        error_message = f"Ran out of retries trying to delete"
        instance.error(error_message)
        instance.boot_volume.error(error_message)
        logger.error(f"{error_message} {instance}")
        return

    # FIXME ... not sure about this.  Should already have sent the
    # Nova server delete request
    delete_instance(instance)
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(
        timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
        _dispose_volume_once_instance_is_deleted, instance,
        archive, retries - 1)


def delete_volume(volume):
    n = get_nectar()
    try:
        n.cinder.volumes.delete(volume.id)
    except cinderclient.exceptions.NotFound:
        logger.info(f"Cinder volume missing for {volume}.  Can't delete it.")
    except cinderclient.exceptions.ClientException:
        logger.exception(f"Cinder volume delete failed for {volume}")
        return False

    # TODO ... should we wait for delete to complete?
    volume.deleted = datetime.now(utc)
    volume.save()
    return True


def delete_backup(volume):
    if not volume.backup_id:
        logger.info(f"No backup to delete for {volume}")
        return True
    n = get_nectar()
    try:
        n.cinder.backups.delete(volume.backup_id)
    except cinderclient.exceptions.NotFound:
        logger.info(f"Cinder backup missing for {volume}.  Can't delete it.")
    except cinderclient.exceptions.ClientException:
        logger.exception(f"Cinder backup delete failed for {volume}")
        return False

    # TODO ... should we wait for the backup deletion to complete?
    volume.backup_id = None
    volume.save()
    return True


def archive_volume_worker(volume, requesting_feature):
    '''
    Archive a volume by creating a Cinder backup then deleting the Cinder
    volume.  Returns True if the backup request was accepted OR if the
    Cinder volume was not found.
    '''

    # This "hides" the volume from the get_volume method allowing
    # another one to be created / launched without errors.
    volume.marked_for_deletion = datetime.now(utc)
    volume.save()

    n = get_nectar()
    try:
        cinder_volume = n.cinder.volumes.get(volume_id=volume.id)
        if cinder_volume.status != VOLUME_AVAILABLE:
            logger.error(
                f"Cannot archive volume with Cinder status "
                f"{cinder_volume.status}: {volume}. Manual cleanup needed.")
            return False
    except cinderclient.exceptions.NotFound:
        volume.error("Cinder volume missing.  Cannot be archived.")
        logger.error(
            f"Cinder volume missing for {volume}. Cannot be archived.")
        return True

    try:
        backup = n.cinder.backups.create(
            volume.id, name=f"{volume.id}-archive")
        logger.info(
            f'Cinder backup {backup.id} started for volume {volume.id}')
    except cinderclient.exceptions.ClientException as e:
        volume.error("Cinder backup failed")
        logger.error(
            f"Cinder backup failed for volume {volume.id}: {e}")
        return False

    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=5), wait_for_backup,
                         volume, backup.id,
                         after_time(ARCHIVE_WAIT_SECONDS))

    # This allows the user to launch a new desktop immediately.
    vm_status = VMStatus.objects.get_vm_status_by_volume(
        volume, requesting_feature, allow_missing=True)
    if vm_status:
        vm_status.status = NO_VM
        vm_status.save()

    return True


def wait_for_backup(volume, backup_id, deadline):
    n = get_nectar()
    try:
        details = n.cinder.backups.get(backup_id)
    except cinderclient.exceptions.NotFound:
        # The backup has disappeared ...
        logger.error(f"Backup {backup_id} for volume {volume} not "
                     "found.  Presumed failed.")
        return

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


def archive_expired_volume(volume, requesting_feature, dry_run=False):
    try:
        vm_status = VMStatus.objects.get_vm_status_by_volume(
            volume, requesting_feature)
        if vm_status.status != VM_SHELVED:
            logger.info(f"Skipping archiving of {volume} "
                        f"in unexpected state: {vm_status}")
        elif not dry_run:
            archive_volume_worker(volume, requesting_feature)
            return True
    except Exception:
        logger.exception(f"Cannot retrieve vm_status for {volume}")
    return False
