import logging

from datetime import datetime, timezone, timedelta

import django_rq
from django.http import Http404
from novaclient.v2.servers import REBOOT_HARD, REBOOT_SOFT

from vm_manager.constants import VM_OKAY, REBOOT_CONFIRM_WAIT_SECONDS, \
    REBOOT_COMPLETE_SECONDS, REBOOT_CONFIRM_RETRIES
from vm_manager.models import Instance, VMStatus
from vm_manager.utils.utils import get_nectar

logger = logging.getLogger(__name__)


def reboot_vm_worker(user, vm_id, reboot_level, requesting_feature):
    instance = Instance.objects.get_instance_by_untrusted_vm_id(
        vm_id, user, requesting_feature)
    volume = instance.boot_volume
    volume.rebooted = datetime.now(timezone.utc)
    volume.save()
    logger.info(f"About to {reboot_level} reboot VM {instance.id} "
                f"for user {user.username}")
    n = get_nectar()
    nova_server = n.nova.servers.get(instance.id)
    if reboot_level == REBOOT_HARD:
        reboot_result = nova_server.reboot(REBOOT_HARD)
    else:
        reboot_result = nova_server.reboot(REBOOT_SOFT)
    logger.info(str(reboot_result))

    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)
    vm_status.status_progress = 33
    vm_status.status_message = "Reboot request sent; waiting for restart"
    vm_status.save()

    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(
        timedelta(seconds=REBOOT_CONFIRM_WAIT_SECONDS),
        check_power_state, REBOOT_CONFIRM_RETRIES,
        instance, requesting_feature)

    return reboot_result


def check_power_state(retries, instance, requesting_feature):
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)
    active = instance.check_active_status()
    if active:
        logger.info(f"VM {instance.id} is ACTIVE")
        # FIXME - we should be waiting for a phone_home from the VM,
        # but the desktop images don't (yet) phone_home on a soft or
        # hard reboot.  In the mean time, we will just assume that the
        # reboot has completed.
        vm_status.status_progress = 66
        vm_status.status_message = "Instance restarted; waiting for reboot"
        vm_status.save()
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(
            timedelta(seconds=REBOOT_COMPLETE_SECONDS),
            wait_for_reboot, instance, requesting_feature)
    elif retries > 0:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(
            timedelta(seconds=REBOOT_CONFIRM_WAIT_SECONDS),
            check_power_state, retries - 1, instance, requesting_feature)
    else:
        msg = "VM {instance.id} has not gone ACTIVE after reboot."
        logger.error(msg)
        vm_status.error(msg)
        vm_status.save()


def wait_for_reboot(instance, requesting_feature):
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)
    logger.info(f"VM {instance.id} should have rebooted by now")
    # FIXME - see above ...
    vm_status.status_progress = 100
    vm_status.status_message = "Reboot has completed"
    vm_status.status = VM_OKAY
    vm_status.save()
