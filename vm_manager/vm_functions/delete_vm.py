import logging
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import django_rq
import novaclient
from django.conf import settings


import vm_manager
from vm_manager.constants import INSTANCE_DELETION_RETRY_WAIT_TIME, INSTANCE_DELETION_RETRY_COUNT, \
    INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME, INSTANCE_CHECK_SHUTOFF_RETRY_COUNT, LINUX
from vm_manager.utils.utils import get_nectar, generate_hostname_url

from guacamole.models import GuacamoleConnection

logger = logging.getLogger(__name__)


def delete_vm_worker(instance):
    logger.info(f"About to delete vm at addr: {instance.get_ip_addr()} "
                f"for user {instance.user.username}")

    n = get_nectar()
    try:
        n.nova.servers.stop(instance.id)
    except novaclient.exceptions.NotFound:
        logger.error(f"Trying to delete an instance that's missing from OpenStack {instance}")

    if instance.boot_volume.operating_system == LINUX:
        # remove the vm from puppet
        _remove_vm_from_puppet(instance)

    # Check if the Instance is Shutoff before requesting OS to Delete it
    logger.info(f"Checking whether {instance} is ShutOff after {INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME} "
                f"seconds and Delete it")
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
                         _check_instance_is_shutoff_and_delete, instance, INSTANCE_CHECK_SHUTOFF_RETRY_COUNT,
                         _delete_volume_once_instance_is_deleted, (instance, INSTANCE_DELETION_RETRY_COUNT))


def _remove_vm_from_puppet(instance):
    parent_dir = os.path.dirname(vm_manager.__file__)
    script_path = Path(f"{parent_dir}/utils/clean_node")
    hostname = generate_hostname_url(instance.boot_volume.hostname_id, instance.boot_volume.operating_system)
    if not script_path.exists():
        logger.error("Could not find puppet cleanup script!")
        return

    p = subprocess.Popen(
        [str(script_path), str(hostname),
         str(parent_dir)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (child_stdout, child_stderr) = p.communicate()
    if p.returncode:
        logger.error(f"clean_node returned: {p.returncode}. "
                     f"Could not delete instance {instance.id} for user {instance.user.username}\n")
        logger.error(f"{os.fsdecode(child_stderr)}")
        return
    logger.info(f'{os.fsdecode(child_stdout).strip()}')
    return


def _check_instance_is_shutoff_and_delete(instance, instance_shutoff_check_retries, func, func_args):
    scheduler = django_rq.get_scheduler('default')
    if not instance.check_shutdown_status() and instance_shutoff_check_retries > 0:
        # If the instance is not Shutoff, schedule the check after 10 seconds
        logger.info(f"{instance} is not shutoff yet! Will check again in "
                    f"{INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME} seconds")
        scheduler.enqueue_in(timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
                             _check_instance_is_shutoff_and_delete, instance, instance_shutoff_check_retries - 1,
                             func, func_args)
        return
    if instance_shutoff_check_retries <= 0:
        logger.info(f"Ran out of retries to check. {instance} took longer to shutoff."
                    f"Proceeding with requesting openstack to Delete instance anyway!")

    # delete instance
    _delete_instance_worker(instance)
    # delete volume
    scheduler.enqueue_in(timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
                         func, *func_args)


def _delete_instance_worker(instance):
    n = get_nectar()
    try:
        n.nova.servers.delete(instance.id)
        logger.info(f"Instructed OpenStack to delete {instance}")
        instance.guac_connection.delete()
    except novaclient.exceptions.NotFound:
        logger.info(f"Instance {instance} already deleted")
    except Exception as e:
        logger.error(f"something went wrong with the instance deletion call for {instance}, it returned {e}")


def _delete_volume_once_instance_is_deleted(instance, instance_deletion_retries):
    n = get_nectar()
    try:
        my_instance = n.nova.servers.get(instance.id)
        if settings.DEBUG:
            print('retries: ', instance_deletion_retries, '; openstack instance:', my_instance)
    except novaclient.exceptions.NotFound:
        logger.info(f"Instance {instance.id} successfully deleted, we can delete the volume now!")
        instance.deleted = datetime.now(timezone.utc)
        instance.save()
        _delete_volume(instance.boot_volume)
        return
    except Exception as e:
        logger.error(f"something went wrong with the instance get call for {instance}, it returned {e}")
        return

    # Openstack still has the instance, and was able to return it to us
    if instance_deletion_retries == 0:
        _delete_instance_worker(instance)
        scheduler = django_rq.get_scheduler('default')
        # Note in this case I'm using `minutes=` not `seconds=` to give a long wait time that should be sufficient
        scheduler.enqueue_in(timedelta(minutes=INSTANCE_DELETION_RETRY_WAIT_TIME),
                             _delete_volume_once_instance_is_deleted, instance, instance_deletion_retries - 1)
        return

    if instance_deletion_retries <= 0:
        error_message = f"ran out of retries trying to delete"
        instance.error(error_message)
        instance.boot_volume.error(error_message)
        logger.error(error_message + " " + instance)
        return

    _delete_instance_worker(instance)
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
                         _delete_volume_once_instance_is_deleted, instance, instance_deletion_retries - 1)


def _delete_volume(volume):
    n = get_nectar()
    delete_result = str(n.cinder.volumes.delete(volume.id))
    volume.deleted = datetime.now(timezone.utc)
    volume.save()
    if settings.DEBUG:
        print(delete_result)
    return
