from datetime import datetime, timedelta
import logging

import django_rq
import novaclient

from django.utils.timezone import utc

from vm_manager.constants import ACTIVE, SHUTDOWN, \
    VM_MISSING, VM_SHELVED, VM_WAITING, VM_OKAY, VM_ERROR, VM_SUPERSIZED, \
    INSTANCE_DELETION_RETRY_WAIT_TIME, INSTANCE_DELETION_RETRY_COUNT, \
    INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME, \
    INSTANCE_CHECK_SHUTOFF_RETRY_COUNT, FORCED_SHELVE_WAIT_SECONDS, \
    WF_SUCCESS, WF_FAIL, WF_RETRY, WF_CONTINUE
from vm_manager.models import VMStatus, Expiration, EXP_EXPIRING, \
    EXP_EXPIRY_FAILED, EXP_EXPIRY_FAILED_RETRYABLE, EXP_EXPIRY_COMPLETED
from vm_manager.utils.expiry import VolumeExpiryPolicy
from vm_manager.utils.utils import get_nectar, after_time
from vm_manager.vm_functions.create_vm import launch_vm_worker
from vm_manager.vm_functions.delete_vm import \
    _check_instance_is_shutoff_and_delete

from guacamole.models import GuacamoleConnection


logger = logging.getLogger(__name__)


def shelve_vm_worker(instance):
    logger.info(f"About to shelve {instance}")

    if instance.guac_connection:
        GuacamoleConnection.objects.filter(instance=instance).delete()
        instance.guac_connection = None
        instance.save()

    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, None, allow_missing=True)

    n = get_nectar()
    try:
        status = n.nova.servers.get(instance.id).status
        if status not in (ACTIVE, SHUTDOWN):
            logger.error(f"Nova instance for {instance} is in unexpected "
                         f"state {status}.  Needs manual cleanup.")
            instance.error(f"Nova instance is {status}")
            if vm_status:
                vm_status.status = VM_ERROR
                vm_status.save()
            return _end_shelve(instance, WF_RETRY)
    except novaclient.exceptions.NotFound:
        logger.error("Trying to shelve an instance that is missing "
                     f"from Nova - {instance}")
        instance.error("Nova instance is missing", gone=True)
        if vm_status:
            vm_status.status = VM_MISSING
            vm_status.save()
        return _end_shelve(instance, WF_SUCCESS)
    except novaclient.exceptions.ClientException:
        logger.exception("Instance get failed - {instance}")
        return _end_shelve(instance, WF_RETRY)

    if status == ACTIVE:
        try:
            n.nova.servers.stop(instance.id)
        except novaclient.exceptions.ClientException:
            logger.exception("Instance stop failed - {instance}")
            return _end_shelve(instance, WF_FAIL)
    else:
        logger.info(f"Instance {instance} already shutdown in Nova.")

    if vm_status:
        vm_status.status = VM_WAITING
        vm_status.wait_time = after_time(FORCED_SHELVE_WAIT_SECONDS)
        vm_status.status_progress = 33
        vm_status.status_message = 'Instance stopping'
        vm_status.save()

    # Confirm instance is ShutOff and then Delete it
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(
        timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
        _check_instance_is_shutoff_and_delete, instance,
        INSTANCE_CHECK_SHUTOFF_RETRY_COUNT,
        _confirm_instance_deleted,
        (instance, INSTANCE_DELETION_RETRY_COUNT))
    return WF_CONTINUE


def _confirm_instance_deleted(instance, retries):
    n = get_nectar()
    try:
        my_instance = n.nova.servers.get(instance.id)
        logger.debug(f"Instance delete status is retries: {retries} "
                     f"openstack instance: {my_instance}")
    except novaclient.exceptions.NotFound:
        logger.info(f"Instance {instance.id} successfully deleted, "
                    f"we can mark the volume as shelved now!")
        now = datetime.now(utc)
        instance.deleted = now
        instance.save()
        volume = instance.boot_volume
        volume.shelved_at = now
        volume.set_expires(VolumeExpiryPolicy().initial_expiry())
        volume.save()
        vm_status = VMStatus.objects.get_vm_status_by_instance(
            instance, None, allow_missing=True)
        if vm_status:
            vm_status.status_progress = 100
            vm_status.status_message = 'Instance shelved'
            vm_status.status = VM_SHELVED
            vm_status.save()
        return _end_shelve(instance, WF_SUCCESS)
    except novaclient.exceptions.ClientException:
        logger.exception(f"Nova instance get failed for {instance}")
        return _end_shelve(instance, WF_FAIL)

    if retries <= 0:
        error_message = (f"ran out of retries trying to "
                         f"terminate shelved instance")
        instance.error(error_message)
        logger.error(f"{error_message} {instance}")
        return _end_shelve(instance, WF_RETRY)
    else:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(
            timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
            _confirm_instance_deleted, instance, retries - 1)
        return WF_CONTINUE


def unshelve_vm_worker(user, desktop_type, zone):
    logger.info(f'Unshelving {desktop_type.id} VM '
                f'for {user.username}')
    return launch_vm_worker(user, desktop_type, zone)


def shelve_expired_vm(instance, requesting_feature):
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature, allow_missing=True)
    if vm_status and vm_status.status not in (VM_OKAY, VM_SUPERSIZED):
        logger.error(f"Instance in unexpected state: {vm_status}")
        return WF_RETRY
    else:
        return shelve_vm_worker(instance)


def _end_shelve(instance, wf_status):
    if instance.expiration:
        expiration = Expiration.objects.get(pk=instance.expiration.pk)
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
