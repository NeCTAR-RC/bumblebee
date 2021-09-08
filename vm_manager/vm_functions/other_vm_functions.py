import logging

from datetime import datetime, timezone, timedelta

import django_rq
from django.http import Http404
from novaclient.v2.servers import REBOOT_HARD, REBOOT_SOFT

from vm_manager.constants import IP_PLACEHOLDER, USERNAME_PLACEHOLDER, DOMAIN_PLACEHOLDER, \
    REBOOT_CONFIRM_WAIT_SECONDS
from vm_manager.models import Instance, VMStatus
from vm_manager.utils.RDP_file import rdp_file
from vm_manager.utils.utils import get_nectar, get_domain

logger = logging.getLogger(__name__)


def reboot_vm_worker(user, vm_id, reboot_level, requesting_feature):
    instance = Instance.objects.get_instance_by_untrusted_vm_id(vm_id, user, requesting_feature)
    volume = instance.boot_volume
    volume.rebooted = datetime.now(timezone.utc)
    volume.save()
    logger.info(f"About to reboot vm at addr: {instance.get_ip_addr()} "
                f"for user {user.username}")
    n = get_nectar()
    nova_server = n.nova.servers.get(instance.id)
    if reboot_level == REBOOT_HARD:
        reboot_result = nova_server.reboot(REBOOT_HARD)
    else:
        reboot_result = nova_server.reboot(REBOOT_SOFT)
    logger.info(str(reboot_result))

    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=REBOOT_CONFIRM_WAIT_SECONDS), check_power_state, instance, requesting_feature)

    return reboot_result


def check_power_state(instance, requesting_feature):
    vm_status = VMStatus.objects.get_vm_status_by_instance(instance, requesting_feature)
    active = instance.check_active_status()
    if not active:
        vm_status.error("Instance not Powered up after Restart")
        vm_status.save()


def get_rdp_file(user, vm_id, requesting_feature):
    instance = Instance.objects.get_instance_by_untrusted_vm_id(vm_id, user, requesting_feature)
    rdp_info = rdp_file.replace(IP_PLACEHOLDER, instance.get_url())\
        .replace(USERNAME_PLACEHOLDER, user.username).replace(DOMAIN_PLACEHOLDER, get_domain(user))
    return rdp_info
