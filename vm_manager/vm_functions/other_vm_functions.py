from datetime import datetime, timedelta
import logging

import django_rq

from django.utils.timezone import utc

from vm_manager.constants import REBOOT_CONFIRM_WAIT_SECONDS, \
    REBOOT_CONFIRM_RETRIES
from vm_manager.models import Instance, VMStatus
from vm_manager.utils.utils import get_nectar

logger = logging.getLogger(__name__)


def reboot_vm_worker(user, vm_id, reboot_level,
                     target_status, requesting_feature):
    instance = Instance.objects.get_instance_by_untrusted_vm_id(
        vm_id, user, requesting_feature)
    volume = instance.boot_volume
    volume.rebooted = datetime.now(utc)
    volume.save()
    logger.info(f"About to {reboot_level} reboot VM {instance.id} "
                f"for user {user.username}")
    n = get_nectar()
    nova_server = n.nova.servers.get(instance.id)
    reboot_result = nova_server.reboot(reboot_level)

    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)
    vm_status.status_progress = 33
    vm_status.status_message = "Reboot request sent; waiting for restart"
    vm_status.save()

    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(
        timedelta(seconds=REBOOT_CONFIRM_WAIT_SECONDS),
        check_power_state, REBOOT_CONFIRM_RETRIES,
        instance, target_status, requesting_feature)

    return reboot_result


def check_power_state(retries, instance, target_status, requesting_feature):
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)
    active = instance.check_active_status()
    if active:
        logger.info(f"Instance {instance.id} is ACTIVE")
        vm_status.status_progress = 66
        vm_status.status_message = "Instance restarted; waiting for reboot"
        vm_status.save()
        # The final stage is done in response to a phone_home request
    elif retries > 0:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(
            timedelta(seconds=REBOOT_CONFIRM_WAIT_SECONDS),
            check_power_state, retries - 1, instance, target_status,
            requesting_feature)
    else:
        msg = "Instance {instance.id} has not gone ACTIVE after reboot."
        logger.error(msg)
        vm_status.error(msg)
        vm_status.save()
