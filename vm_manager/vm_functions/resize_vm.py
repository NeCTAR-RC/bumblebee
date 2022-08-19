import logging
from datetime import datetime, timedelta

from django.utils.timezone import utc
import django_rq
import novaclient

from vm_manager.constants import \
    RESIZE, VERIFY_RESIZE, ACTIVE, \
    RESIZE_CONFIRM_WAIT_SECONDS, FORCED_DOWNSIZE_WAIT_SECONDS, \
    VM_SUPERSIZED, VM_RESIZING, VM_OKAY, \
    WF_SUCCESS, WF_FAIL, WF_RETRY, WF_STARTED, WF_CONTINUE
from vm_manager.utils.utils import after_time, get_nectar
from vm_manager.utils.expiry import BoostExpiryPolicy
from vm_manager.models import VMStatus, Instance, Resize, \
    EXP_EXPIRING, EXP_EXPIRY_COMPLETED, EXP_EXPIRY_FAILED, \
    EXP_EXPIRY_FAILED_RETRYABLE

logger = logging.getLogger(__name__)


def supersize_vm_worker(instance, desktop_type) -> str:
    logger.info(f"About to supersize {desktop_type.id} instance "
                f"for user {instance.user.username} to "
                f"flavor {desktop_type.big_flavor_name}")
    supersize_result = _resize_vm(instance,
                                  desktop_type.big_flavor.id,
                                  VM_SUPERSIZED, desktop_type.feature)
    if supersize_result in (WF_SUCCESS, WF_STARTED):
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
    if downsize_result in (WF_SUCCESS, WF_STARTED):
        resize = Resize.objects.get_latest_resize(instance.id)
        if not resize:
            logger.error("Missing resize record for instance {instance}")
            return WF_FAIL
        else:
            resize.reverted = datetime.now(utc)
            resize.save()
    return downsize_result


# TODO - Analyse for possible race conditions with supersize/downsize
# This would be with a expiry downsize ...
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
    return WF_SUCCESS


def _resize_vm(instance, flavor, target_status, requesting_feature):
    n = get_nectar()
    try:
        server = n.nova.servers.get(instance.id)
    except novaclient.exceptions.NotFound:
        logger.error(f"Trying to resize {instance} but it is not "
                     "found in Nova.")
        instance.error("Nova instance is missing")
        return WF_FAIL

    if server.status != ACTIVE:
        logger.error(f"Nova instance for {instance} in unexpected state "
                     f"{server.status}.  Needs manual cleanup.")
        instance.error(f"Nova instance state is {server.status}")
        return WF_FAIL

    current_flavor = server.flavor['id']
    if current_flavor == str(flavor):
        logger.error(f"Instance {instance.id} already has flavor {flavor}. "
                     "Skipping the resize.")
        vm_status = VMStatus.objects.get_vm_status_by_instance(
            instance, requesting_feature)
        vm_status.status = target_status
        vm_status.save()
        return WF_SUCCESS

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
    return WF_STARTED


def _wait_to_confirm_resize(instance, flavor, target_status,
                            deadline, requesting_feature):
    n = get_nectar()
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, requesting_feature)
    logger.debug(f"vm_status: {vm_status}")

    status = instance.get_status()
    if status == VERIFY_RESIZE:
        logger.info(f"Confirming resize of {instance}")
        try:
            n.nova.servers.confirm_resize(instance.id)
        except novaclient.exception.ClientException:
            logger.exception(f"Instance resize confirm failed for {instance}")
            return end_resize(instance, target_status, WF_FAIL)

        if target_status == VM_OKAY:
            resize = Resize.objects.get_latest_resize(instance.id)
            resize.reverted = datetime.now(utc)
            resize.save()
        vm_status.status_progress = 66
        vm_status.status_message = "Resize completed; waiting for reboot"
        vm_status.save()
        logger.debug(f"new vm_status: {vm_status}")
        # The final step is done in response to a phone_home request
        return WF_CONTINUE

    elif status == RESIZE:
        logger.info(f"Waiting for resize of {instance}")
        if datetime.now(utc) < deadline:
            scheduler = django_rq.get_scheduler('default')
            scheduler.enqueue_in(timedelta(seconds=5),
                                 _wait_to_confirm_resize,
                                 instance, flavor, target_status, deadline,
                                 requesting_feature)
            return WF_CONTINUE
        else:
            logger.error("Resize has taken too long")

    elif status == ACTIVE:
        try:
            resized_instance = n.nova.servers.get(instance.id)
            instance_flavor = resized_instance.flavor['id']
        except novaclient.exceptions.ClientException:
            logger.exception(f"Instance get failed for {instance}")
            return end_resize(instance, target_status, WF_FAIL)

        if instance_flavor != str(flavor):
            message = (
                f"Instance ({instance}) resize failed as "
                f"instance hasn't changed flavor: "
                f"Actual Flavor: {instance_flavor}, "
                f"Expected Flavor: {flavor}")
            logger.error(message)
            vm_status.error(message)
            logger.debug(f"new vm_status: {vm_status}")
            return end_resize(instance, target_status, WF_FAIL)

        logger.info(f"Resize of {instance} was confirmed automatically")
        if target_status == VM_OKAY:
            resize = Resize.objects.get_latest_resize(instance.id)
            resize.reverted = datetime.now(utc)
            resize.save()
        vm_status.status_progress = 66
        vm_status.status_message = "Resize completed; waiting for reboot"
        vm_status.save()
        logger.debug(f"new vm_status: {vm_status}")
        # The final step is done in response to a phone_home request
        return WF_CONTINUE

    message = (
        f"Instance ({instance}) resize failed instance in state: {status}")
    logger.error(message)
    vm_status.error(message)
    logger.debug(f"new vm_status: {vm_status}")
    return end_resize(instance, target_status, WF_FAIL)


def end_resize(instance, target_status, wf_status):
    if target_status == VM_OKAY:
        # This is a downsize so the Resize should exist ...
        resize = Resize.objects.get_latest_resize(instance.id)
        assert resize is not None
        if resize.expiration and resize.expiration.stage == EXP_EXPIRING:
            if wf_status == WF_FAIL:
                resize.expiration.stage = EXP_EXPIRY_FAILED
            elif wf_status == WF_RETRY:
                resize.expiration.stage = EXP_EXPIRY_FAILED_RETRYABLE
            elif wf_status == WF_SUCCESS:
                resize.expiration.stage = EXP_EXPIRY_COMPLETED
            resize.expiration.stage_date = datetime.now(utc)
            resize.expiration.save()
    return wf_status


def downsize_expired_vm(resize, requesting_feature):
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        resize.instance, requesting_feature, allow_missing=True)
    if vm_status and vm_status.status != VM_SUPERSIZED:
        # There may be cleanup needed, but we are only concerned with
        # the downsizing here.
        logger.info(f"Skipping downsize of instance in wrong state: "
                    f"{vm_status}")
        return WF_SUCCESS
    else:
        result = _resize_vm(resize.instance,
                            resize.instance.boot_volume.flavor,
                            VM_OKAY, requesting_feature)
        if result in (WF_SUCCESS, WF_STARTED):
            resize.reverted = datetime.now(utc)
            resize.save()
            if vm_status:
                # Refetch because _resize_vm may have updated it
                vm_status = VMStatus.objects.get(pk=vm_status.pk)
                if vm_status.status == VM_SUPERSIZED:
                    if result == WF_STARTED:
                        # Simulate vm_status behavior of a normal downsize
                        # (with # longer timeout) in case user does a
                        # browser refresh while auto-downsize is happening.
                        vm_status.wait_time = after_time(
                            FORCED_DOWNSIZE_WAIT_SECONDS)
                        vm_status.status_progress = 0
                        vm_status.status_message = "Forced downsize starting"
                        vm_status.status = VM_RESIZING
                    else:
                        vm_status.status = VM_OKAY
                    vm_status.save()
        return result
