from datetime import datetime, timedelta, timezone
import logging

import django_rq
import novaclient

from django.conf import settings

from vm_manager.constants import ACTIVE, SHUTDOWN, REBOOT_HARD
from vm_manager.models import Instance, VMStatus
from vm_manager.utils.utils import get_nectar

logger = logging.getLogger(__name__)


def reboot_vm_worker(user, vm_id, reboot_level,
                     target_status, requesting_feature):
    instance = Instance.objects.get_instance_by_untrusted_vm_id(
        vm_id, user, requesting_feature)
    n = get_nectar()
    try:
        nova_server = n.nova.servers.get(instance.id)
        if nova_server.status == ACTIVE:
            pass
        elif nova_server.status == SHUTDOWN:
            logger.info(f"Forcing {REBOOT_HARD} reboot because Nova instance "
                        f"was in state {nova_server.status}")
            reboot_level = REBOOT_HARD
        else:
            logger.error(f"Nova instance for {instance} in unexpected state "
                         f"{nova_server.status}.  Needs manual cleanup.")
            instance.error(f"Nova instance state is {nova_server.status}")
            return
    except novaclient.exceptions.NotFound:
        logger.error(f"Nova instance is missing for {instance}")
        instance.error("Nova instance is missing")
        return

    volume = instance.boot_volume
    volume.rebooted_at = datetime.now(timezone.utc)
    volume.save()

    logger.info(f"Performing {reboot_level} reboot on {instance}")
    reboot_result = nova_server.reboot(reboot_level)

    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)
    vm_status.status_progress = 33
    vm_status.status_message = "Reboot request sent; waiting for restart"
    vm_status.save()

    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(
        timedelta(seconds=settings.REBOOT_CONFIRM_WAIT),
        _check_power_state, settings.REBOOT_CONFIRM_RETRIES,
        instance, target_status, requesting_feature)

    return reboot_result


def _check_power_state(retries, instance, target_status, requesting_feature):
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)
    active = instance.check_active_status()
    if active:
        logger.info(f"Instance {instance.id} is {ACTIVE}")
        vm_status.status_progress = 66
        vm_status.status_message = "Instance restarted; waiting for reboot"
        vm_status.save()
        # The final stage is done in response to a phone_home request
    elif retries > 0:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(
            timedelta(seconds=settings.REBOOT_CONFIRM_WAIT),
            _check_power_state, retries - 1, instance, target_status,
            requesting_feature)
    else:
        msg = f"Instance {instance.id} has not gone {ACTIVE} after reboot"
        logger.error(msg)
        vm_status.error(msg)
