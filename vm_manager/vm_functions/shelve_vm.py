import django_rq
import novaclient
import logging
from datetime import datetime, timezone, timedelta

from django.conf import settings
from vm_manager.constants import INSTANCE_DELETION_RETRY_WAIT_TIME, INSTANCE_DELETION_RETRY_COUNT, VM_SHELVED, \
    INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME, INSTANCE_CHECK_SHUTOFF_RETRY_COUNT
from vm_manager.vm_functions.delete_vm import _delete_instance_worker, _check_instance_is_shutoff_and_delete
from vm_manager.vm_functions.create_vm import launch_vm_worker
from vm_manager.models import VMStatus
from vm_manager.utils.utils import get_nectar

logger = logging.getLogger(__name__)


def shelve_vm_worker(instance, requesting_feature):
    logger.info(f"About to shelve {instance.boot_volume.operating_system} vm at addr: "
                f"{instance.get_ip_addr()} for user {instance.user.username}")

    n = get_nectar()
    try:
        n.nova.servers.stop(instance.id)
    except novaclient.exceptions.NotFound:
        logger.error(f"Trying to shelve an instance that's missing from OpenStack {instance}")

    # Confirm instance is ShutOff and then Delete it
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
                         _check_instance_is_shutoff_and_delete, instance, INSTANCE_CHECK_SHUTOFF_RETRY_COUNT,
                         _confirm_instance_deleted, (instance, INSTANCE_DELETION_RETRY_COUNT, requesting_feature))


def _confirm_instance_deleted(instance, instance_deletion_retries, requesting_feature):
    n = get_nectar()
    try:
        my_instance = n.nova.servers.get(instance.id)
        logger.debug(f"Instance delete status is retries: {instance_deletion_retries} "
                     f"openstack instance: {my_instance}")
    except novaclient.exceptions.NotFound:
        logger.info(f"Instance {instance.id} successfully deleted, "
                    f"we can mark the volume as shelved now!")
        instance.deleted = datetime.now(timezone.utc)
        instance.save()
        volume = instance.boot_volume
        volume.shelved = True
        volume.save()
        vm_status = VMStatus.objects.get_vm_status_by_instance(instance, requesting_feature)
        vm_status.status = VM_SHELVED
        vm_status.save()
        return
    except Exception as e:
        logger.error(f"something went wrong with the get instance call for {instance}, it returned {e}")
        return

    # Openstack still has the instance, and was able to return it to us
    if instance_deletion_retries == 0:
        _delete_instance_worker(instance)
        scheduler = django_rq.get_scheduler('default')
        # Note in this case I'm using `minutes=` not `seconds=` to give a long wait time that should be sufficient
        scheduler.enqueue_in(timedelta(minutes=INSTANCE_DELETION_RETRY_WAIT_TIME),
                             _confirm_instance_deleted, instance, instance_deletion_retries - 1, requesting_feature)
        return

    if instance_deletion_retries <= 0:
        error_message = f"ran out of retries trying to shelve"
        instance.error(error_message)
        logger.error(error_message + " " + instance)
        return

    _delete_instance_worker(instance)
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
                         _confirm_instance_deleted, instance, instance_deletion_retries - 1, requesting_feature)


def unshelve_vm_worker(user, vm_info, requesting_feature):
    logger.info(f'Unshelving {vm_info["operating_system"]} VM for {user.username}')
    launch_vm_worker(user, vm_info, requesting_feature)
