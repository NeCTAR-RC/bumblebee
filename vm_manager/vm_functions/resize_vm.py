import logging
from datetime import datetime, timedelta, timezone
import django_rq

from vm_manager.constants import DOWNSIZE_PERIOD, \
    RESIZE_CONFIRM_WAIT_SECONDS, VM_SUPERSIZED, VM_RESIZING, VM_OKAY
from vm_manager.utils.utils import after_time, get_nectar
from vm_manager.models import VMStatus, Instance, Resize

logger = logging.getLogger(__name__)


def supersize_vm_worker(instance, desktop_type) -> str:
    logger.info(f"About to supersize {desktop_type.id} vm "
                f"for user {instance.user.username}")
    supersize_result = _resize_vm(instance,
                                  desktop_type.big_flavor.id,
                                  desktop_type.feature)
    resize = Resize(instance=instance,
                    expires=calculate_supersize_expiration_date(
                        datetime.now(timezone.utc).date()))
    resize.save()
    return supersize_result


def downsize_vm_worker(instance, desktop_type) -> str:
    logger.info(f"About to downsize {desktop_type.id} vm "
                f"for user {instance.user.username}")
    downsize_result = _resize_vm(instance,
                                 desktop_type.default_flavor.id,
                                 desktop_type.feature)

    resize = Resize.objects.get_latest_resize(instance.id)
    if not resize:
        logger.error("Missing resize record for instance {instance}")
    else:
        resize.reverted = datetime.now(timezone.utc)
        resize.save()
    return downsize_result


# TODO - This is not wired up.  I think it really belongs in
# vm_manager.views because it doesn't involve any asynchrony.
# TODO - Analyse for possible race conditions with supersize/downsize
def extend(user, vm_id, requesting_feature) -> str:
    instance = Instance.objects.get_instance_by_untrusted_vm_id(
        vm_id, user, requesting_feature)
    logger.info(f"Extending the expiration of "
                f"{instance.boot_volume.operating_system} vm "
                f"for user {user.username}")
    resize = Resize.objects.get_latest_resize(instance.id)
    if not resize or resize.reverted:
        message = f"No Resize is current for instance {instance}"
        logger.error(message)
        return message
    exp_date = resize.expires
    if not can_extend_supersize_period(exp_date):
        message = f"Resize (id {resize.id}) date too far in future: {exp_date}"
        logger.error(message)
        return message
    resize.expires = calculate_supersize_expiration_date(exp_date)
    resize.save()
    return str(resize)


def _resize_vm(instance, flavor_id, requesting_feature):
    n = get_nectar()
    current_flavor_id = n.nova.servers.get(instance.id).flavor.id
    if current_flavor_id == flavor_id:
        message = (
            f"Instance {instance.id} already has flavor {flavor_id}. "
            f"Skipping the resize.")
        logger.error(message)
        return message

    resize_result = n.nova.servers.resize(instance.id, flavor_id)
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=5),
                         _wait_to_confirm_resize,
                         instance, flavor_id,
                         after_time(RESIZE_CONFIRM_WAIT_SECONDS),
                         requesting_feature)
    return resize_result


def _wait_to_confirm_resize(instance, flavor_id, deadline, requesting_feature):
    status = VM_OKAY if flavor == str(instance.boot_volume.flavor) \
        else VM_SUPERSIZED
    n = get_nectar()
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)

    if instance.check_verify_resize_status():
        logger.info(f"Confirming resize of {instance}")
        n.nova.servers.confirm_resize(instance.id)
        vm_status.status = status
        vm_status.save()
        return str(vm_status)

    elif instance.check_resizing_status():
        logger.info(f"Waiting for resize of {instance}")
        if datetime.now(timezone.utc) < deadline:
            scheduler = django_rq.get_scheduler('default')
            scheduler.enqueue_in(timedelta(seconds=5),
                                 _wait_to_confirm_resize,
                                 instance, flavor_id, deadline,
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

        if instance_flavor != str(flavor_id):
            error_message = \
                f"Instance ({instance}) resize failed as " \
                f"instance hasn't changed flavor: " \
                f"Actual Flavor: {instance_flavor}, " \
                f"Expected Flavor: {flavor}"
            logger.error(error_message)
            vm_status.error(error_message)
            vm_status.save()
            return error_message

        log_message = \
            f"Resize of {instance} has already been confirmed automatically"
        logger.info(log_message)
        vm_status.status = status
        vm_status.save()
        return log_message

    error_message = \
        f"Instance ({instance}) resize failed instance in " \
        f"state: {instance.get_status()}"
    logger.error(error_message)
    vm_status.error(error_message)
    vm_status.save()
    return error_message


def calculate_supersize_expiration_date(date):
    return date + timedelta(days=DOWNSIZE_PERIOD)


def can_extend_supersize_period(date):
    return date < (datetime.now(timezone.utc).date()
                   + timedelta(days=DOWNSIZE_PERIOD))


def downsize_expired_supersized_vms(requesting_feature):
    try:
        resizes = Resize.objects.filter(
            reverted=None, instance__marked_for_deletion=None,
            expires__lte=datetime.now(timezone.utc).date())
    except Resize.DoesNotExist:
        return None
    for resize in resizes:
        _resize_vm(resize.instance, resize.instance.boot_volume.flavor,
                   requesting_feature)
        resize.reverted = datetime.now(timezone.utc)
        resize.save()
        vm_status = VMStatus.objects.get_vm_status_by_instance(
            resize.instance, requesting_feature)
        vm_status.status = VM_RESIZING
        vm_status.save()
    logger.info(f"Downsized {len(resizes)} instances")
    return len(resizes)
