import logging
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import django_rq
import novaclient

import vm_manager
from vm_manager.constants import INSTANCE_DELETION_RETRY_WAIT_TIME, \
    INSTANCE_DELETION_RETRY_COUNT, \
    INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME, \
    INSTANCE_CHECK_SHUTOFF_RETRY_COUNT, LINUX
from vm_manager.models import VMStatus
from vm_manager.utils.utils import get_nectar

from guacamole.models import GuacamoleConnection


logger = logging.getLogger(__name__)


def delete_vm_worker(instance):
    logger.info(f"About to delete vm at addr: {instance.get_ip_addr()} "
                f"for user {instance.user.username}")

    if instance.guac_connection:
        GuacamoleConnection.objects.filter(instance=instance).delete()
        instance.guac_connection = None
        instance.save()

    n = get_nectar()
    try:
        n.nova.servers.stop(instance.id)
    except novaclient.exceptions.NotFound:
        logger.error(f"Trying to delete an instance that's missing "
                     f"from OpenStack {instance}")

    # Check if the Instance is Shutoff before requesting OS to Delete it
    logger.info(f"Checking whether {instance} is ShutOff "
                f"after {INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME} "
                f"seconds and Delete it")
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(
        timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
        _check_instance_is_shutoff_and_delete, instance,
        INSTANCE_CHECK_SHUTOFF_RETRY_COUNT,
        _delete_volume_once_instance_is_deleted,
        (instance, INSTANCE_DELETION_RETRY_COUNT))


def _check_instance_is_shutoff_and_delete(
        instance, retries, func, func_args):
    scheduler = django_rq.get_scheduler('default')
    if not instance.check_shutdown_status() and retries > 0:
        # If the instance is not Shutoff, schedule the recheck
        logger.info(f"{instance} is not shutoff yet! Will check again in "
                    f"{INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME} seconds")
        scheduler.enqueue_in(
            timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
            _check_instance_is_shutoff_and_delete, instance,
            retries - 1, func, func_args)
        return
    if retries <= 0:
        # TODO - not sure we should delete the instance anyway ...
        logger.info(f"Ran out of retries. {instance} shutoff took too long."
                    f"Proceeding to delete Openstack instance anyway!")

    # Delete the instance
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, instance.boot_volume.requesting_feature)
    vm_status.status_progress = 66
    # Hack: since this won't be displayed when we are deleting a
    # desktop, use the progress message for the shelving case.
    vm_status.status_message = 'Instance shelving'
    vm_status.save()
    _delete_instance_worker(instance)

    # The 'func' will do the next step; e.g. delete the volume
    # or mark the volume as shelved.
    scheduler.enqueue_in(
        timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
        func, *func_args)


def _delete_instance_worker(instance):
    n = get_nectar()
    instance.marked_for_deletion = datetime.now(timezone.utc)
    instance.save()
    try:
        n.nova.servers.delete(instance.id)
        logger.info(f"Instructed OpenStack to delete {instance}")
    except novaclient.exceptions.NotFound:
        logger.info(f"Instance {instance} already deleted")
    except Exception as e:
        logger.error(f"something went wrong with the instance deletion "
                     f"call for {instance}, it raised {e}")


def _delete_volume_once_instance_is_deleted(instance, retries):
    n = get_nectar()
    try:
        my_instance = n.nova.servers.get(instance.id)
        logger.debug(f"Instance delete status is retries: {retries} "
                     f"openstack instance: {my_instance}")
    except novaclient.exceptions.NotFound:
        logger.info(f"Instance {instance.id} successfully deleted, "
                    f"we can delete the volume now!")
        instance.deleted = datetime.now(timezone.utc)
        instance.save()
        delete_volume(instance.boot_volume)
        return
    except Exception as e:
        logger.error(f"something went wrong with the instance get "
                     f"call for {instance}, it raised {e}")
        return

    # Openstack still has the instance, and was able to return it to us
    if retries == 0:
        _delete_instance_worker(instance)
        scheduler = django_rq.get_scheduler('default')
        # Note in this case I'm using `minutes=` not `seconds=` to give
        # a long wait time that should be sufficient
        scheduler.enqueue_in(
            timedelta(minutes=INSTANCE_DELETION_RETRY_WAIT_TIME),
            _delete_volume_once_instance_is_deleted, instance,
            retries - 1)
        return

    if retries <= 0:
        error_message = f"ran out of retries trying to delete"
        instance.error(error_message)
        instance.boot_volume.error(error_message)
        logger.error(f"{error_message} {instance}")
        return

    _delete_instance_worker(instance)
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(
        timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
        _delete_volume_once_instance_is_deleted, instance, retries - 1)


def delete_volume(volume):
    n = get_nectar()
    delete_result = str(n.cinder.volumes.delete(volume.id))
    # TODO ... should set to mark for deletion, then wait for delete
    # to complete
    volume.deleted = datetime.now(timezone.utc)
    volume.save()
    logger.debug(f"Delete result is {delete_result}")
    return
