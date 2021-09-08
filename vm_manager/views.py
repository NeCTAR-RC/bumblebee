import django_rq
import logging

from datetime import datetime, timedelta, timezone
from math import ceil

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, Http404
from django.template import loader
from django.urls import reverse
from django.utils.html import format_html
from operator import itemgetter

from vm_manager.models import VMStatus, Instance, Resize

from vm_manager.constants import VM_ERROR, VM_OKAY, VM_WAITING, VM_SHELVED, NO_VM, VM_SHUTDOWN, \
    VM_SUPERSIZED, VM_DELETED, VM_CREATING, VM_MISSING, VM_RESIZING, LAUNCH_WAIT_SECONDS, \
    CLOUD_INIT_FINISHED, CLOUD_INIT_STARTED, REBOOT_WAIT_SECONDS, RESIZE_WAIT_SECONDS, SHELVE_WAIT_SECONDS

from vm_manager.constants import SCRIPT_ERROR, SCRIPT_OKAY
from vm_manager.utils.utils import generate_hostname

# These are all needed, as they're consumed by researcher_workspace/views.py
from vm_manager.vm_functions.admin_functionality import test_function, admin_worker, start_downsizing_cron_job, \
    vm_report_for_page, vm_report_for_csv, db_check
from vm_manager.vm_functions.create_vm import launch_vm_worker
from vm_manager.vm_functions.delete_vm import delete_vm_worker
from vm_manager.vm_functions.other_vm_functions import get_rdp_file, reboot_vm_worker
from vm_manager.vm_functions.shelve_vm import shelve_vm_worker, unshelve_vm_worker
from vm_manager.vm_functions.resize_vm import can_extend_supersize_period, calculate_supersize_expiration_date, \
    supersize_vm_worker, downsize_vm_worker, extend, downsize_expired_supersized_vms

logger = logging.getLogger(__name__)


def launch_vm(user, vm_info, requesting_feature) -> str:
    operating_system = vm_info['operating_system']

    vm_status = VMStatus.objects.get_latest_vm_status(user, operating_system, requesting_feature)
    if vm_status and vm_status.status != VM_DELETED:
        error_message = f"A VMStatus for {user} and {operating_system} already exists"
        logger.error(error_message)
        return error_message

    vm_status = VMStatus(user=user, requesting_feature=requesting_feature, operating_system=operating_system, status=VM_CREATING,
                         wait_time=datetime.now(timezone.utc) + timedelta(seconds=LAUNCH_WAIT_SECONDS))
    vm_status.save()

    # Check for race condition in previous statements and delete duplicate VMStatus
    check_vm_status = VMStatus.objects.filter(user=user, operating_system=operating_system, requesting_feature=requesting_feature)\
        .exclude(status__in=[NO_VM, VM_SHELVED])
    if check_vm_status.count() > 1:
        vm_status.delete()
        error_message = f"A VMStatus with that User and OS already exists"
        logger.error(error_message)
        return error_message

    queue = django_rq.get_queue('default')
    queue.enqueue(launch_vm_worker, user=user, vm_info=vm_info, requesting_feature=requesting_feature)

    return str(vm_status)


def delete_vm(user, vm_id, requesting_feature) -> str:
    vm_status = VMStatus.objects.get_vm_status_by_untrusted_vm_id(vm_id, user, requesting_feature)
    if (not vm_status) or vm_status.status == NO_VM:
        error_message = f"No VMStatus found with that vm_id or vm already marked as deleted {user} {vm_id} {vm_status}"
        logger.error(error_message)
        return error_message
    logger.info(f"Changing the VMStatus of {vm_id} from {vm_status.status} to {VM_DELETED} and Mark for Deletion is set"
                f" on the Instance and Volume {vm_status.instance.boot_volume.id}")
    vm_status.status = VM_DELETED
    vm_status.save()
    vm_status.instance.set_marked_for_deletion()
    vm_status.instance.boot_volume.set_marked_for_deletion()

    queue = django_rq.get_queue('default')
    queue.enqueue(delete_vm_worker, vm_status.instance)

    return str(vm_status)


@login_required(login_url='login')
def admin_delete_vm(request, vm_id):
    if not request.user.is_superuser:
        raise Http404()

    try:
        vm_status = VMStatus.objects.get(instance=vm_id)
    except VMStatus.DoesNotExist:
        error_message = f"No VMStatus found with that vm_id when trying to admin delete Instance {vm_id}"
        logger.error(error_message)
        return error_message
    logger.info(f"Performing Admin delete on {vm_id} Mark for Deletion is set"
                f" on the Instance and Volume {vm_status.instance.boot_volume.id}")
    vm_status.status = VM_DELETED
    vm_status.save()
    vm_status.instance.set_marked_for_deletion()
    vm_status.instance.boot_volume.set_marked_for_deletion()

    queue = django_rq.get_queue('default')
    queue.enqueue(delete_vm_worker, vm_status.instance)

    logger.info(f"{request.user} admin deleted vm {vm_id}")
    return HttpResponseRedirect(reverse('admin:vm_manager_instance_change', args=(vm_id,)))


def shelve_vm(user, vm_id, requesting_feature) -> str:
    vm_status = VMStatus.objects.get_vm_status_by_untrusted_vm_id(vm_id, user, requesting_feature)
    if vm_status and not (vm_status.status == VM_OKAY or vm_status.status == VM_SUPERSIZED):
        error_message = f"A VMStatus {vm_id} for {user} is in the wrong state. VM cannot be shelved"
        logger.error(error_message)
        return error_message

    logger.info(f"Changing the VMStatus of {vm_id} from {vm_status.status} to {VM_WAITING} and Mark for Deletion is set"
                f" on the Instance")
    vm_status.wait_time = datetime.now(timezone.utc) + timedelta(seconds=SHELVE_WAIT_SECONDS)
    vm_status.status = VM_WAITING
    vm_status.save()
    vm_status.instance.set_marked_for_deletion()

    queue = django_rq.get_queue('default')
    queue.enqueue(shelve_vm_worker, vm_status.instance, requesting_feature)

    return str(vm_status)


def unshelve_vm(user, vm_info, requesting_feature) -> str:
    operating_system = vm_info['operating_system']

    vm_status = VMStatus.objects.get_latest_vm_status(user, operating_system, requesting_feature)
    if not vm_status or vm_status.status != VM_SHELVED:
        error_message = f"A VMStatus for {user} and {operating_system} is in the wrong state. VM cannot be unshelved"
        logger.error(error_message)
        return error_message

    vm_status = VMStatus(user=user, requesting_feature=requesting_feature, operating_system=operating_system, status=VM_CREATING,
                         wait_time=datetime.now(timezone.utc) + timedelta(seconds=LAUNCH_WAIT_SECONDS))
    vm_status.save()

    queue = django_rq.get_queue('default')
    queue.enqueue(unshelve_vm_worker, user=user, vm_info=vm_info, requesting_feature=requesting_feature)

    return str(vm_status)


def reboot_vm(user, vm_id, reboot_level, requesting_feature) -> str:
    vm_status = VMStatus.objects.get_vm_status_by_untrusted_vm_id(vm_id, user, requesting_feature)
    vm_status.wait_time = datetime.now(timezone.utc)+timedelta(seconds=REBOOT_WAIT_SECONDS)
    vm_status.save()

    queue = django_rq.get_queue('default')
    queue.enqueue(reboot_vm_worker, user, vm_id, reboot_level, requesting_feature)

    return str(vm_status)


def supersize_vm(user, vm_id, flavor, requesting_feature) -> str:
    vm_status = VMStatus.objects.get_vm_status_by_untrusted_vm_id(vm_id, user, requesting_feature)

    if vm_status and vm_status.status != VM_OKAY:
        error_message = f"Instance {vm_id} for {user} is not in the right state to Supersize"
        logger.error(error_message)
        return error_message

    vm_status.status = VM_RESIZING
    vm_status.wait_time = datetime.now(timezone.utc) + timedelta(seconds=RESIZE_WAIT_SECONDS)
    vm_status.save()

    queue = django_rq.get_queue('default')
    queue.enqueue(supersize_vm_worker, instance=vm_status.instance, flavor=flavor,
                  requesting_feature=requesting_feature)

    return str(vm_status)


def downsize_vm(user, vm_id, requesting_feature) -> str:
    vm_status = VMStatus.objects.get_vm_status_by_untrusted_vm_id(vm_id, user, requesting_feature)

    if vm_status and vm_status.status != VM_SUPERSIZED:
        error_message = f"Instance {vm_id} for {user} is not in the right state to Downsize"
        logger.error(error_message)
        return error_message

    vm_status.status = VM_RESIZING
    vm_status.wait_time = datetime.now(timezone.utc) + timedelta(seconds=RESIZE_WAIT_SECONDS)
    vm_status.save()

    queue = django_rq.get_queue('default')
    queue.enqueue(downsize_vm_worker, instance=vm_status.instance, requesting_feature=requesting_feature)

    return str(vm_status)


def get_vm_state(user, operating_system, requesting_feature):
    vm_status = VMStatus.objects.get_latest_vm_status(user, operating_system, requesting_feature)
    logger.debug("Status: %s", str(vm_status))
    if (not vm_status) or (vm_status.status == VM_DELETED):
        return NO_VM, "No VM", None
    if vm_status.status == VM_ERROR:
        if vm_status.instance:
            return VM_ERROR, "VM has Errored", vm_status.instance.id
        else:
            return VM_MISSING, "VM has Errored", None
    curr_time = datetime.now(timezone.utc)
    if vm_status.wait_time > curr_time:  # We have to wait longer
        return VM_WAITING, str(ceil((vm_status.wait_time - curr_time).seconds)), None
    if vm_status.status == VM_WAITING and vm_status.wait_time < curr_time:  # Status is still VM_Waiting but time is up
        if vm_status.instance:
            vm_status.error(f"VM {vm_status.instance.id} not ready at {vm_status.wait_time} timeout")
            return VM_ERROR, "VM Not Ready", vm_status.instance.id
        else:
            vm_status.status = VM_ERROR
            vm_status.save()
            logger.error(f"VM is missing at timeout {vm_status.id}, {user}, {operating_system}")
            return VM_MISSING, "VM has Errored", None
    if vm_status.status == VM_SHELVED:
        return VM_SHELVED, "VM SHELVED", vm_status.instance.id
    if vm_status.instance.check_shutdown_status():
        return VM_SHUTDOWN, "VM Shutdown", vm_status.instance.id
    if not vm_status.instance.check_active_or_resize_statuses():
        vm_status.instance.error("Error at Openstack level. Status:" + vm_status.instance.get_status())
        return VM_ERROR, "Error at Openstack level", vm_status.instance.id
    if vm_status.status == VM_OKAY:
        return VM_OKAY, {'url': vm_status.instance.get_url()}, vm_status.instance.id
    if vm_status.status == VM_SUPERSIZED:
        resize = Resize.objects.get_latest_resize(vm_status.instance)
        return VM_SUPERSIZED, {'url': vm_status.instance.get_url(),
                               'is_eligible': can_extend_supersize_period(resize.expires),
                               'expires': resize.expires,
                               'extended_expiration': calculate_supersize_expiration_date(resize.expires)},\
            vm_status.instance.id
    logger.error(f"get_vm_state for to an unhandled state for {user} requesting {operating_system}")
    raise NotImplementedError


def render_vm(request, user, operating_system, requesting_feature, buttons_to_display):
    state, what_to_show, vm_id = get_vm_state(user, operating_system, requesting_feature)
    app_name = requesting_feature.app_name

    #if (state == VM_OKAY or state == VM_SUPERSIZED)
    #    what_to_show['url'] = reverse(app_name + ':get_rdp_file', args=[vm_id])

    if state == VM_SUPERSIZED and what_to_show["is_eligible"]:
        messages.info(request, format_html(f'Your {str(operating_system).capitalize()} vm is set to resize '
                  f'back to the default size on {what_to_show["expires"]}'))

    vm_module = loader.render_to_string(f'vm_manager/html/{state}.html',
                {'what_to_show': what_to_show, 'operating_system': operating_system, 'vm_id': vm_id,
                 "buttons_to_display": buttons_to_display, "app_name": app_name,
                 "requesting_feature": requesting_feature}, request)

    script = loader.render_to_string(f'vm_manager/javascript/{state}.js',
                {'what_to_show': what_to_show, 'operating_system': operating_system, 'vm_id': vm_id,
                 "buttons_to_display": buttons_to_display, "app_name": app_name,
                 "requesting_feature": requesting_feature}, request)
    return vm_module, script


def notify_vm(request, requesting_feature):
    ip_address = request.GET.get("ip")
    hostname = request.GET.get("hn")
    operating_system = request.GET.get("os")
    state = int(request.GET.get("state"))
    msg = request.GET.get("msg")
    instance = Instance.objects.get_instance_by_ip_address(ip_address, requesting_feature)
    if not instance:
        logger.error(f"No current Instance found with ip address {ip_address}")
        raise Http404
    volume = instance.boot_volume
    if generate_hostname(volume.hostname_id, volume.operating_system) != hostname:
        logger.error(f"Hostname provided in request does not match hostname of volume {instance}, {hostname}")
        raise Http404
    if state == SCRIPT_OKAY:
        if msg == CLOUD_INIT_FINISHED:
            volume.ready = True
            volume.save()
            vm_status = VMStatus.objects.get_vm_status_by_instance(instance, requesting_feature)
            vm_status.status = VM_OKAY
            vm_status.save()
        elif msg == CLOUD_INIT_STARTED:
            volume.checked_in = True
            volume.save()
    else:
        vm_status = VMStatus.objects.get_vm_status_by_instance(instance, requesting_feature)
        vm_status.error(msg)
        logger.error(f"notify_vm error: {msg} for instance: \"{instance}\"")
    result = f"{ip_address}, {operating_system}, {state}, {msg}"
    logger.info(result)
    return result


def rd_report_for_user(user, operating_systems, requesting_feature):
    rd_report_info = {}
    for operating_system in operating_systems:
        vms = Instance.objects.filter(user=user, boot_volume__operating_system=operating_system,
                                      boot_volume__requesting_feature=requesting_feature).order_by('created')
        deleted = [{'date': vm.marked_for_deletion, 'count': -1} for vm in vms.order_by('marked_for_deletion') if vm.marked_for_deletion]
        created = [{'date': vm.created, 'count': 1} for vm in vms]
        vm_info = sorted(created + deleted, key=itemgetter('date'))
        count = 0
        vm_graph = []
        for date_obj in vm_info:
            vm_graph.append({'date': date_obj['date'], 'count': count})
            count += date_obj['count']
            date_obj['count'] = count
            vm_graph.append(date_obj)
        vm_graph.append({'date': datetime.now(timezone.utc), 'count': count})
        rd_report_info[operating_system] = vm_graph
    return {'user_vm_info': rd_report_info}
