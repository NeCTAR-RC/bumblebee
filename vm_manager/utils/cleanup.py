from datetime import datetime, timedelta, timezone
import logging

import novaclient

from django.conf import settings

from vm_manager.constants import ACTIVE, SHUTDOWN, NO_VM, VM_SHELVED
from vm_manager.models import Instance, VMStatus, Resize, Expiration, \
    EXP_EXPIRING, EXP_EXPIRY_FAILED_RETRYABLE, EXP_EXPIRY_COMPLETED
from vm_manager.utils.expiry import VolumeExpiryPolicy
from vm_manager.utils.utils import get_nectar

logger = logging.getLogger(__name__)

utc = timezone.utc


def cleanup_stuck_terminations(dry_run=False):
    """Clean up desktops whose shelve or delete workflow died.

    Both the shelve and delete workflows mark the Instance for deletion
    up front, tell Nova to delete it, and poll until it disappears.  If
    the poll budget runs out (or the rq worker dies), the desktop is left
    errored even though Nova usually completes the delete eventually,
    stranding the desktop in an error state that needs manual repair.

    This job sweeps instances that have been marked for deletion for
    longer than any live workflow could still be running, and per Nova
    state:

    - gone: complete the bookkeeping the workflow would have done
      (record the shelve, or the instance deletion for a delete);
    - SHUTOFF: re-issue the delete request; the next run completes
      the bookkeeping;
    - ACTIVE: re-issue the stop request so a later run can delete it
      after a clean shutdown;
    - anything else: leave it for manual cleanup, as the workflows do.

    Volume disposal for a dead delete workflow is not attempted: whether
    the volume was to be archived or deleted is not recorded, so that is
    left to the admin delete/archive actions.

    Returns a dict of counts of the actions taken.
    """
    cutoff = (datetime.now(utc)
              - timedelta(seconds=settings.TERMINATION_CLEANUP_AGE))
    stuck = Instance.objects.filter(
        deleted=None, marked_for_deletion__lt=cutoff)
    counts = {'checked': 0, 'completed': 0, 'deleted': 0, 'stopped': 0,
              'skipped': 0, 'failed': 0}
    n = get_nectar()
    for instance in stuck:
        counts['checked'] += 1
        try:
            status = n.nova.servers.get(instance.id).status
        except novaclient.exceptions.NotFound:
            logger.info("Completing termination bookkeeping for %s",
                        instance)
            if not dry_run:
                _complete_termination(instance)
            counts['completed'] += 1
            continue
        except novaclient.exceptions.ClientException:
            logger.exception("Nova instance get failed for %s", instance)
            counts['failed'] += 1
            continue

        if status == SHUTDOWN:
            logger.info("Re-issuing Nova delete for stuck %s", instance)
            if not dry_run:
                try:
                    n.nova.servers.delete(instance.id)
                except novaclient.exceptions.ClientException:
                    logger.exception(
                        "Nova instance delete failed for %s", instance)
                    counts['failed'] += 1
                    continue
            counts['deleted'] += 1
        elif status == ACTIVE:
            logger.info("Re-issuing Nova stop for stuck %s", instance)
            if not dry_run:
                try:
                    n.nova.servers.stop(instance.id)
                except novaclient.exceptions.ClientException:
                    logger.exception(
                        "Nova instance stop failed for %s", instance)
                    counts['failed'] += 1
                    continue
            counts['stopped'] += 1
        else:
            logger.error("Nova instance for stuck %s is in unexpected "
                         "state %s. Needs manual cleanup.", instance, status)
            counts['skipped'] += 1
    return counts


def _complete_termination(instance):
    """Do the bookkeeping a dead shelve or delete workflow left undone.

    The Nova instance is gone.  Mirrors the tail ends of the shelve and
    delete workflows (and the admin repair action): record the instance
    as deleted, revert any live resize, and either mark the volume as
    shelved or leave a marked-for-deletion volume to the delete workflow
    and admin actions.
    """
    now = datetime.now(utc)
    volume = instance.boot_volume
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, None, allow_missing=True)

    resize = Resize.objects.get_latest_resize(instance)
    if resize and not resize.reverted:
        resize.reverted = now
        resize.save()

    instance.deleted = now
    instance.error_flag = None
    instance.error_message = None
    instance.save()

    if volume.deleted or volume.marked_for_deletion:
        # A delete workflow owned this instance.  The volume still needs
        # to be disposed of via the admin delete/archive actions.
        logger.info("Recorded %s as deleted; %s is left for the admin "
                    "delete/archive actions", instance, volume)
        if vm_status and vm_status.status != NO_VM:
            vm_status.status = NO_VM
            vm_status.save()
    else:
        logger.info("Recorded %s as deleted and %s as shelved",
                    instance, volume)
        volume.shelved_at = now
        volume.set_expires(VolumeExpiryPolicy().initial_expiry())
        volume.save()
        if vm_status:
            vm_status.status = VM_SHELVED
            vm_status.status_progress = 100
            vm_status.status_message = 'Instance shelved'
            vm_status.save()

    if instance.expiration:
        # An expiry-driven shelve would otherwise be retried (or need
        # admin attention) even though it has now completed.
        expiration = Expiration.objects.get(pk=instance.expiration.pk)
        if expiration.stage in (EXP_EXPIRING, EXP_EXPIRY_FAILED_RETRYABLE):
            expiration.stage = EXP_EXPIRY_COMPLETED
            expiration.stage_date = now
            expiration.save()
