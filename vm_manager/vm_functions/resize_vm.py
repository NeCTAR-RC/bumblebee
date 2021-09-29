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
    resize.reverted = datetime.now(timezone.utc)
    resize.save()
    return downsize_result


def extend(user, vm_id, requesting_feature) -> str:
    instance = Instance.objects.get_instance_by_untrusted_vm_id(
        vm_id, user, requesting_feature)
    logger.info(f"Extending the expiration of "
                f"{instance.boot_volume.operating_system} vm "
                f"for user {user.username}")
    resize = Resize.objects.get_latest_resize(instance.id)
    expiration_date = resize.expires
    if not can_extend_supersize_period(expiration_date):
        error_message = f"Resize {resize.id} date too far " \
                        f"in future: {expiration_date}"
        logger.error(error_message)
        return error_message
    resize.expires = calculate_supersize_expiration_date(expiration_date)
    resize.save()
    return str(resize)


def _resize_vm(instance, flavor, requesting_feature):
    n = get_nectar()
    resize_result = n.nova.servers.resize(instance.id, flavor)
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=5),
                         _wait_to_confirm_resize,
                         instance, flavor,
                         after_time(RESIZE_CONFIRM_WAIT_SECONDS),
                         requesting_feature)
    return resize_result


def _wait_to_confirm_resize(instance, flavor, deadline, requesting_feature):
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
                                 instance, flavor, deadline,
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
