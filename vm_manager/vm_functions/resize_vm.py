import logging
from datetime import datetime, timedelta

from django.utils.timezone import utc
import django_rq
import novaclient

from vm_manager.constants import \
    RESIZE, VERIFY_RESIZE, ACTIVE, \
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
    if supersize_result:
        now = datetime.now(utc)
        resize = Resize(instance=instance, requested=now)
        resize.set_expires(BoostExpiryPolicy().initial_expiry(now=now))
    return supersize_result


def downsize_vm_worker(instance, desktop_type) -> str:
    logger.info(f"About to downsize {desktop_type.id} instance "
                f"for user {instance.user.username} to "
                f"flavor {desktop_type.default_flavor_name}")
    downsize_result = _resize_vm(instance,
                                 desktop_type.default_flavor.id,
                                 VM_OKAY, desktop_type.feature)
    if downsize_result:
        resize = Resize.objects.get_latest_resize(instance.id)
        if not resize:
            logger.error("Missing resize record for instance {instance}")
        else:
            resize.reverted = datetime.now(utc)
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
    resize.set_expires(BoostExpiryPolicy().new_expiry(resize))
    resize.save()
    return str(resize)


def _resize_vm(instance, flavor, target_status, requesting_feature):
    n = get_nectar()
    try:
        server = n.nova.servers.get(instance.id)
    except novaclient.exceptions.NotFound:
        logger.error(f"Trying to resize {instance} but it is not "
                     "found in Nova.")
        instance.error("Nova instance is missing")
        return False

    if server.status != ACTIVE:
        logger.error(f"Nova instance for {instance} in unexpected state "
                     f"{server.status}.  Needs manual cleanup.")
        instance.error(f"Nova instance state is {server.status}")
        return False

    current_flavor = server.flavor['id']
    if current_flavor == str(flavor):
        logger.error(f"Instance {instance.id} already has flavor {flavor}. "
                     "Skipping the resize.")
        vm_status = VMStatus.objects.get_vm_status_by_instance(
            instance, requesting_feature)
        vm_status.status = target_status
        vm_status.save()
        return False

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
    return True


def _wait_to_confirm_resize(instance, flavor, target_status,
                            deadline, requesting_feature):
    n = get_nectar()
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)
    logger.debug(f"vm_status: {vm_status}")

    status = instance.get_status()
    if status == VERIFY_RESIZE:
        logger.info(f"Confirming resize of {instance}")
        n.nova.servers.confirm_resize(instance.id)
        vm_status.status_progress = 66
        vm_status.status_message = "Resize completed; waiting for reboot"
        vm_status.save()
        logger.debug(f"new vm_status: {vm_status}")

        # The final step is done in response to a phone_home request
        return str(vm_status)

    elif status == RESIZE:
        logger.info(f"Waiting for resize of {instance}")
        if datetime.now(utc) < deadline:
            scheduler = django_rq.get_scheduler('default')
            scheduler.enqueue_in(timedelta(seconds=5),
                                 _wait_to_confirm_resize,
                                 instance, flavor, target_status, deadline,
                                 requesting_feature)
            return str(vm_status)
        else:
            logger.error("Resize has taken too long")

    elif status == ACTIVE:
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
            logger.debug(f"new vm_status: {vm_status}")
            return message

        message = f"Resize of {instance} was confirmed automatically"
        logger.info(message)
        vm_status.status_progress = 66
        vm_status.status_message = "Resize completed; waiting for reboot"
        vm_status.save()
        logger.debug(f"new vm_status: {vm_status}")
        # The final step is done in response to a phone_home request
        return message

    message = (
        f"Instance ({instance}) resize failed instance in state: {status}")
    logger.error(message)
    vm_status.error(message)
    vm_status.save()
    logger.debug(f"new vm_status: {vm_status}")
    return message


def downsize_expired_vm(resize, requesting_feature):
    try:
        vm_status = VMStatus.objects.get_vm_status_by_instance(
            resize.instance, requesting_feature)
        if vm_status.status != VM_SUPERSIZED:
            logger.info(f"Skipping downsize of instance in wrong state: "
                        f"{vm_status}")
        else:
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
            resize.reverted = datetime.now(utc)
            resize.save()
            return True
    except Exception:
        logger.exception(
            f"Cannot retrieve vm_status for {resize.instance}")

    return False
