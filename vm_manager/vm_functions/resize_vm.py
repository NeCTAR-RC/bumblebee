import logging
from datetime import datetime, timedelta, timezone
import django_rq

from vm_manager.constants import REBOOT_COMPLETE_SECONDS, \
    RESIZE_CONFIRM_WAIT_SECONDS, FORCED_DOWNSIZE_WAIT_SECONDS, \
    VM_SUPERSIZED, VM_RESIZING, VM_OKAY
from vm_manager.utils.utils import after_time, get_nectar
from vm_manager.utils.expiry import BoostExpiryPolicy
from vm_manager.models import VMStatus, Instance, Resize

logger = logging.getLogger(__name__)


def supersize_vm_worker(instance, desktop_type) -> str:
    logger.info(f"About to supersize {desktop_type.id} instance "
                f"for user {instance.user.username} to "
                f"flavor {desktop_type.big_flavor_name}")
    supersize_result = _resize_vm(instance,
                                  desktop_type.big_flavor.id,
                                  VM_SUPERSIZED, desktop_type.feature)
    now = datetime.now(timezone.utc)
    resize = Resize(instance=instance,
                    requested=now,
                    expires=BoostExpiryPolicy().initial_expiry(now=now))
    resize.save()
    return supersize_result


def downsize_vm_worker(instance, desktop_type) -> str:
    logger.info(f"About to downsize {desktop_type.id} instance "
                f"for user {instance.user.username} to "
                f"flavor {desktop_type.default_flavor_name}")
    downsize_result = _resize_vm(instance,
                                 desktop_type.default_flavor.id,
                                 VM_OKAY, desktop_type.feature)

    resize = Resize.objects.get_latest_resize(instance.id)
    if not resize:
        logger.error("Missing resize record for instance {instance}")
    else:
        resize.reverted = datetime.now(timezone.utc)
        resize.save()
    return downsize_result


# TODO - Analyse for possible race conditions with supersize/downsize
def extend_boost(user, vm_id, requesting_feature) -> str:
    instance = Instance.objects.get_instance_by_untrusted_vm_id(
        vm_id, user, requesting_feature)
    logger.info(f"Extending the expiration of "
                f"{instance.boot_volume.operating_system} instance "
                f"for user {user.username}")
    resize = Resize.objects.get_latest_resize(instance.id)
    if not resize or resize.reverted:
        message = f"No current resize job for instance {instance}"
        logger.error(message)
        return message
    resize.expires = BoostExpiryPolicy().new_expiry(resize)
    resize.save()
    return str(resize)


def _resize_vm(instance, flavor, target_status, requesting_feature):
    n = get_nectar()
    server = n.nova.servers.get(instance.id)
    current_flavor = server.flavor['id']
    if current_flavor == str(flavor):
        message = (
            f"Instance {instance.id} already has flavor {flavor}. "
            f"Skipping the resize.")
        logger.error(message)
        vm_status = VMStatus.objects.get_vm_status_by_instance(
            instance, requesting_feature)
        vm_status.status = target_status
        vm_status.save()
        return message

    resize_result = n.nova.servers.resize(instance.id, flavor)
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)
    vm_status.status_progress = 33
    vm_status.status_message = "Resize initiated; waiting to confirm"
    vm_status.save()
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=5),
                         _wait_to_confirm_resize,
                         instance, flavor, target_status,
                         after_time(RESIZE_CONFIRM_WAIT_SECONDS),
                         requesting_feature)
    return resize_result


def _wait_to_confirm_resize(instance, flavor, target_status,
                            deadline, requesting_feature):
    n = get_nectar()
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)

    if instance.check_verify_resize_status():
        logger.info(f"Confirming resize of {instance}")
        n.nova.servers.confirm_resize(instance.id)
        vm_status.status_progress = 66
        vm_status.status_message = "Resize completed; waiting for reboot"
        vm_status.save()
        # The final step is done in response to a phone_home request
        return str(vm_status)

    elif instance.check_resizing_status():
        logger.info(f"Waiting for resize of {instance}")
        if datetime.now(timezone.utc) < deadline:
            scheduler = django_rq.get_scheduler('default')
            scheduler.enqueue_in(timedelta(seconds=5),
                                 _wait_to_confirm_resize,
                                 instance, flavor, target_status, deadline,
                                 requesting_feature)
            return str(vm_status)
        else:
            logger.error("Resize has taken too long")

    elif instance.check_active_status():
        try:
            resized_instance = n.nova.servers.get(instance.id)
            instance_flavor = resized_instance.flavor['id']
        except Exception as e:
            logger.error(f"Something went wrong with the instance get call "
                         f"for {instance}: it raised {e}")
            return

        if instance_flavor != str(flavor):
            message = (
                f"Instance ({instance}) resize failed as "
                f"instance hasn't changed flavor: "
                f"Actual Flavor: {instance_flavor}, "
                f"Expected Flavor: {flavor}")
            logger.error(message)
            vm_status.error(message)
            vm_status.save()
            return message

        message = f"Resize of {instance} was confirmed automatically"
        logger.info(message)
        vm_status.status_progress = 66
        vm_status.status_message = "Resize completed; waiting for reboot"
        vm_status.save()
        # The final step is done in response to a phone_home request
        return message

    message = (
        f"Instance ({instance}) resize failed instance in "
        f"state: {instance.get_status()}")
    logger.error(message)
    vm_status.error(message)
    vm_status.save()
    return message


# TODO - The current implementation will potentially fire off
# a number of simultaneous downsizes.  Assuming that this method
# is asynchronous, it could send the resizes one by one, and wait
# for each resize to complete (or fail) before starting the next one.
def downsize_expired_supersized_vms(requesting_feature, dry_run=False):
    resizes = Resize.objects.filter(
        reverted=None, instance__marked_for_deletion=None,
        expires__lte=datetime.now(timezone.utc))

    resize_count = 0
    for resize in resizes:
        try:
            vm_status = VMStatus.objects.get_vm_status_by_instance(
                resize.instance, requesting_feature)
        except Exception:
            logger.exception(
                f"Cannot retrieve vm_status for {resize.instance}")
            continue
        if vm_status.status != VM_SUPERSIZED:
            logger.info(f"Skipping downsize of instance in wrong state: "
                        f"{vm_status}")
            continue
        if not dry_run:
            # Simulate the vm_status behavior of a normal downsize (with a
            # longer timeout) in case the user does a browser refresh while
            # the auto-downsize is happening.
            vm_status.wait_time = after_time(FORCED_DOWNSIZE_WAIT_SECONDS)
            vm_status.status_progress = 0
            vm_status.status_message = "Forced downsize starting"
            vm_status.status = VM_RESIZING
            vm_status.save()
            _resize_vm(resize.instance, resize.instance.boot_volume.flavor,
                       VM_OKAY, requesting_feature)
            resize.reverted = datetime.now(timezone.utc)
            resize.save()
        resize_count += 1
    return resize_count
