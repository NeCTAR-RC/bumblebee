import django_rq
import novaclient
import logging
from datetime import datetime, timezone, timedelta

from django.conf import settings
from vm_manager.constants import INSTANCE_DELETION_RETRY_WAIT_TIME, \
    INSTANCE_DELETION_RETRY_COUNT, VM_SHELVED, \
    INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME, \
    INSTANCE_CHECK_SHUTOFF_RETRY_COUNT
from vm_manager.vm_functions.delete_vm import _delete_instance_worker, \
    _check_instance_is_shutoff_and_delete
from vm_manager.vm_functions.create_vm import launch_vm_worker
from vm_manager.models import VMStatus
from vm_manager.utils.utils import get_nectar

logger = logging.getLogger(__name__)


def shelve_vm_worker(instance, requesting_feature):
    logger.info(f"About to shelve {instance.boot_volume.operating_system} "
                f"vm at addr: {instance.get_ip_addr()} "
                f"for user {instance.user.username}")

    n = get_nectar()
    try:
        n.nova.servers.stop(instance.id)
    except novaclient.exceptions.NotFound:
        logger.error(f"Trying to shelve an instance that's missing "
                     f"from OpenStack {instance}")

    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)
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
        (instance, INSTANCE_DELETION_RETRY_COUNT, requesting_feature))


def _confirm_instance_deleted(instance, retries, requesting_feature):
    n = get_nectar()
    try:
        my_instance = n.nova.servers.get(instance.id)
        logger.debug(f"Instance delete status is retries: "
                     f"{instance_deletion_retries} "
                     f"openstack instance: {my_instance}")
    except novaclient.exceptions.NotFound:
        logger.info(f"Instance {instance.id} successfully deleted, "
                    f"we can mark the volume as shelved now!")
        instance.deleted = datetime.now(timezone.utc)
        instance.save()
        volume = instance.boot_volume
        volume.shelved = True
        volume.save()
        vm_status = VMStatus.objects.get_vm_status_by_instance(
            instance, requesting_feature)
        vm_status.status_progress = 100
        vm_status.staus_message = 'Instance shelved'
        vm_status.status = VM_SHELVED
        vm_status.save()
        return
    except Exception as e:
        logger.error(f"something went wrong with the get instance call "
                     f"for {instance}, it returned {e}")
        return

    if retries <= 0:
        error_message = (f"ran out of retries trying to "
                         f"terminate shelved instance")
        instance.error(error_message)
        logger.error(error_message + " " + instance)
    else:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(
            timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
            _confirm_instance_deleted, instance,
            retries - 1, requesting_feature)


def unshelve_vm_worker(user, desktop_type, zone):
    logger.info(f'Unshelving {desktop_type.id} VM '
                f'for {user.username}')
    launch_vm_worker(user, desktop_type, zone)
