from datetime import datetime, timezone
import logging
from operator import itemgetter
from uuid import UUID

from django.conf import settings
from django.contrib import messages
from django.core.mail import mail_managers
from django.db.models import Count
from django.db.models.functions import TruncDay
from django.http import HttpResponse, Http404
from django.shortcuts import render

import cinderclient
import django_rq
import novaclient

from guacamole.models import GuacamoleConnection
from researcher_desktop.models import DesktopType
from researcher_workspace.utils import offset_month_and_year
from vm_manager.constants import VM_DELETED, VM_WAITING, \
    VM_ERROR, VM_OKAY, VM_MISSING, VM_SUPERSIZED, NO_VM, VM_SHELVED,  \
    VOLUME_AVAILABLE, VOLUME_IN_USE, ACTIVE
from vm_manager.models import Instance, Resize, Volume, VMStatus
from vm_manager.utils.Check_ResearchDesktop_Availability import \
    check_availability
from vm_manager.utils.expiry import VolumeExpiryPolicy
from vm_manager.utils.utils import after_time, get_nectar
from vm_manager.vm_functions.delete_vm import \
    delete_vm_worker, delete_volume, archive_volume_worker
from vm_manager.vm_functions.resize_vm import downsize_vm_worker
from vm_manager.vm_functions.shelve_vm import shelve_vm_worker

logger = logging.getLogger(__name__)

utc = timezone.utc


# Not currently wired ...
def test_function(request):
    if not request.user.is_superuser:
        raise Http404()
    return HttpResponse(_generate_weekly_availability_report(),
                        content_type='text/plain')


class _Reporter(object):

    def __init__(self, request):
        self.request = request
        self.errors = False
        self.repairs = False

    def error(self, message):
        logger.error(message)
        messages.error(self.request, message, extra_tags='error')
        self.errors = True

    def repair(self, message):
        logger.info(message)
        messages.info(self.request, message)
        self.repairs = True

    def info(self, message):
        logger.info(message)
        messages.info(self.request, message)


#
# Note that the 'repair' functions only change the Bumblebee to make
# it consistent with Cinder and Nova resources.  They don't change things
# on the Openstack side.  That kind of problem needs to be fixed via
# the Openstack dashboard or CLI.  The Bumblebee admin UI will tell you
# that "manual cleanup" is required.
#


def admin_repair_volume_error(
        request, volume, rep=None,
        expected_states=[VOLUME_AVAILABLE, VOLUME_IN_USE]):
    if not rep:
        rep = _Reporter(request)
    n = get_nectar()
    try:
        status = n.cinder.volumes.get(volume.id).status
        if status not in expected_states:
            rep.error(
                f"Cinder volume {volume.id} is in unexpected "
                f"state {status}. Manual cleanup required.")
            return False
    except cinderclient.exceptions.NotFound:
        rep.repair(f"Cinder volume {volume.id} is missing. "
                   "Recording desktop as deleted.")
        volume.deleted = datetime.now(utc)
        volume.save()

    if volume.error_flag and not volume.deleted:
        volume.error_flag = None
        volume.error_message = None
        volume.save()
        rep.repair(f"Cleared error for volume {volume.id}")

    if not rep.errors and not rep.repairs:
        rep.info(f"Volume {volume.id} has no issues")

    return True


def admin_repair_instance_error(request, instance):
    rep = _Reporter(request)
    n = get_nectar()
    volume = instance.boot_volume
    try:
        status = n.nova.servers.get(instance.id).status
        if volume.deleted:
            rep.error(f"Nova instance {instance.id} still exists for "
                      f"deleted volume {volume.id}. "
                      "Manual cleanup required.")
            return False
        elif not admin_repair_volume_error(
                request, volume, rep, expected_states=[VOLUME_IN_USE]):
            rep.error(f"Volume error for instance {instance.id} "
                      "must be dealt with first.")
            return False
        else:
            if status not in [ACTIVE]:
                rep.error(
                    f"Nova instance {instance.id} is in unexpected "
                    f"state {status}. Manual cleanup required.")
                return False
    except novaclient.exceptions.NotFound:
        if not admin_repair_volume_error(
                request, volume, rep, expected_states=[VOLUME_AVAILABLE]):
            rep.error(f"Volume error for instance {instance.id} "
                      "must be dealt with first.")
            return False

        vmstatus = VMStatus.objects.get_vm_status_by_instance(
            instance, volume.requesting_feature)
        now = datetime.now(utc)
        resize = Resize.objects.get_latest_resize(instance)
        if resize and not resize.reverted:
            rep.repair(f"Reverting resize for instance {instance.id}.")
            resize.reverted = now
            resize.save()
        if not volume.deleted:
            rep.repair(f"Nova instance {instance.id} missing. "
                       "Recording desktop as shelved.")
            volume.shelved_at = now
            volume.set_expires(VolumeExpiryPolicy().initial_expiry())
            volume.save()
            vmstatus.status = VM_SHELVED
        else:
            rep.repair(f"Recording instance {instance.id} as deleted.")
            vmstatus.status = NO_VM
        vmstatus.save()
        instance.deleted = now
        instance.save()

    if instance.error_flag and not instance.deleted:
        instance.error_flag = None
        instance.error_message = None
        instance.save()
        rep.repair(f"Cleared error for instance {instance.id}")

    if not rep.errors and not rep.repairs:
        rep.info(f"Instance {instance.id} has no issues")
    return True


def admin_check_vmstatus(request, vmstatus):
    rep = _Reporter(request)
    instance = vmstatus.instance
    if not vmstatus.instance:
        rep.error(f"VMStatus {vmstatus.id} has no instance")
        return

    volume = instance.boot_volume
    if not volume:
        rep.error(f"VMStatus {vmstatus.id} has an instance "
                  f"({vmstatus.instance.id}) with no boot volume")
        return

    n = get_nectar()
    latest_vmstatus = VMStatus.objects.filter(instance=instance) \
                                      .latest("created")

    if vmstatus.id != latest_vmstatus.id:
        rep.error(f"VMStatus {vmstatus.id} for "
                  f"volume {vmstatus.instance.boot_volume.id} "
                  f"instance {vmstatus.instance.id} is not current.")
        return

    if vmstatus.status in [VM_ERROR, VM_MISSING, NO_VM, VM_DELETED]:
        rep.error(f"VMStatus {vmstatus.id} in state {vmstatus.status} "
                  f"for instance {instance.id}")
        try:
            server = n.nova.servers.get(instance.id)
            rep.error(
                f"Found nova instance {vmstatus.instance.id} "
                f"in state {server.status}")
        except novaclient.exceptions.NotFound:
            rep.error(
                f"No nova instance {vmstatus.instance.id}")
        try:
            vol = n.cinder.volumes.get(volume.id)
            rep.error(
                f"Found cinder volume {volume.id} "
                f"in state {vol.status}")
        except cinderclient.exceptions.NotFound:
            rep.error(
                f"No cinder volume {volume.id}")

    elif vmstatus.status in [VM_OKAY, VM_SUPERSIZED]:
        try:
            status = n.nova.servers.get(instance.id).status
            if status != ACTIVE:
                rep.error(
                    f"Found nova instance {instance.id} in "
                    f"state {status} for a {vmstatus.status} vmstatus")
            resize = Resize.objects.get_latest_resize(instance)
            if vmstatus.status == VM_SUPERSIZED:
                if not resize:
                    rep.error(
                        "Missing Resize for supersized "
                        f"instance {instance.id}")
                elif resize.reverted:
                    rep.error(
                        "Reverted Resize for supersized "
                        f"instance {instance.id}")
            else:
                if resize and not resize.reverted:
                    rep.error(
                        "Unreverted Resize for normal sized "
                        f"instance {instance.id}")
            # Here we could check that the instance's flavor is correct
        except novaclient.exceptions.NotFound:
            rep.error(
                f"Missing nova instance {instance.id} "
                f"for a {vmstatus.status} vmstatus")
    elif vmstatus.status == VM_SHELVED:
        try:
            status = n.nova.servers.get(instance.id).status
            rep.error(
                f"Found nova instance {instance.id} "
                f"in state {status} for a {vmstatus.status} vmstatus")
        except novaclient.exceptions.NotFound:
            pass
        try:
            status = n.cinder.volumes.get(volume.id).status
            if status != VOLUME_AVAILABLE:
                rep.error(
                    f"Cinder volume {volume.id} is "
                    f"in state {status} for a {VM_SHELVED} vmstatus")
        except cinderclient.exceptions.NotFound:
            rep.error(
                f"Cinder volume {volume.id} is missing "
                f"for a {VM_SHELVED} vmstatus")
    else:
        # This includes VM_SHUTDOWN
        rep.error(
            f"VMStatus {vmstatus.id} in unknown state: "
            f"{vmstatus.status}")

    if not rep.errors:
        rep.info(f"VMStatus {vmstatus.id} has no issues")


def admin_delete_instance_and_volume(request, instance):
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, None, allow_missing=True)

    if vm_status:
        vm_status.status = VM_DELETED
        vm_status.save()

    volume = instance.boot_volume
    if instance.deleted:
        volume.set_marked_for_deletion()
        delete_volume(volume)
        logger.info(f"{request.user} admin deleted volume {volume.id}")
    else:
        instance.set_marked_for_deletion()
        volume.set_marked_for_deletion()
        queue = django_rq.get_queue('default')
        queue.enqueue(delete_vm_worker, instance)
        logger.info(
            f"{request.user} admin deleting instance {instance.id} "
            f"and volume {volume.id}")


def admin_archive_instance_and_volume(request, instance):
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, None, allow_missing=True)

    if vm_status:
        vm_status.status = VM_DELETED
        vm_status.save()

    volume = instance.boot_volume
    if instance.deleted:
        volume.set_marked_for_deletion()
        archive_volume_worker(volume, volume.requesting_feature)
        logger.info(f"{request.user} admin archived volume {volume.id}")
    else:
        instance.set_marked_for_deletion()
        volume.set_marked_for_deletion()
        queue = django_rq.get_queue('default')
        queue.enqueue(delete_vm_worker, instance, archive=True)
        logger.info(
            f"{request.user} admin archiving instance {instance.id} "
            f"and volume {volume.id}")


def admin_delete_volume(request, volume):
    vm_status = VMStatus.objects.get_vm_status_by_volume(
        volume, volume.requesting_feature, allow_missing=True)

    if vm_status:
        vm_status.status = VM_DELETED
        vm_status.save()

    volume.set_marked_for_deletion()
    delete_volume(volume)
    logger.info(f"{request.user} admin deleted volume {volume.id}")


def admin_archive_volume(request, volume):
    vm_status = VMStatus.objects.get_vm_status_by_volume(
        volume, volume.requesting_feature, allow_missing=True)

    if vm_status:
        vm_status.status = VM_DELETED
        vm_status.save()

    archive_volume_worker(volume, volume.requesting_feature)
    logger.info(f"{request.user} admin archiving volume {volume.id}")


def admin_shelve_instance(request, instance):
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, None, allow_missing=True)

    if vm_status:
        vm_status.wait_time = after_time(settings.SHELVE_WAIT)
        vm_status.status = VM_WAITING
        vm_status.status_progress = 0
        vm_status.status_message = "Starting desktop shelve"
        vm_status.save()
    instance.set_marked_for_deletion()

    queue = django_rq.get_queue('default')
    queue.enqueue(shelve_vm_worker, instance)

    logger.info(f"{request.user} admin shelved vm {instance.id}")


def admin_downsize_resize(request, resize):
    instance = resize.instance
    vm_status = VMStatus.objects.get_vm_status_by_instance(
        instance, None, allow_missing=True)

    if vm_status:
        vm_status.wait_time = after_time(settings.RESIZE_WAIT)
        vm_status.status = VM_WAITING
        vm_status.status_progress = 0
        vm_status.status_message = "Starting desktop downsize"
        vm_status.save()

    desktop_type = DesktopType.objects.get_desktop_type(
        instance.boot_volume.operating_system)
    queue = django_rq.get_queue('default')
    queue.enqueue(downsize_vm_worker, instance, desktop_type)

    logger.info(f"{request.user} admin downsizing vm {instance.id}")


def db_check(request):
    n = get_nectar()
    nova_servers = n.nova.servers.list()
    cinder_volumes = n.cinder.volumes.list()

    db_deleted_instances = Instance.objects.exclude(deleted=None) \
                                           .values_list('id', flat=True)
    deleted_instances = [
        (server.id, server.name, server.metadata.get('environment', ''))
        for server in nova_servers
            if UUID(server.id) in db_deleted_instances]

    db_deleted_volumes = Volume.objects.exclude(deleted=None) \
                                       .values_list('id', flat=True)
    deleted_volumes = [
        (volume.id, volume.name, volume.metadata.get('environment',
                                                     volume.name[-1]))
        for volume in cinder_volumes
            if UUID(volume.id) in db_deleted_volumes]

    db_instances = Instance.objects.filter(deleted=None) \
                                   .values_list('id', flat=True)
    missing_instances = [
        (server.id, server.name, server.metadata.get('environment', ''))
        for server in nova_servers if UUID(server.id) not in db_instances]

    db_volumes = Volume.objects.filter(deleted=None) \
                               .values_list('id', flat=True)
    missing_volumes = [
        (volume.id, volume.name, volume.metadata.get('environment',
                                                     volume.name[-1]))
        for volume in cinder_volumes if UUID(volume.id) not in db_volumes]

    live_connections = set(
        Instance.objects.filter(deleted=None, marked_for_deletion=None)
        .values_list('guac_connection', flat=True))

    orphaned_connections = [
        (connection.connection_id, connection.connection_name)
        for connection in GuacamoleConnection.objects.all()
        if connection.connection_id not in live_connections]

    return render(request, 'vm_manager/db_check.html',
                  {'missing_instances': missing_instances,
                   'missing_volumes': missing_volumes,
                   'deleted_instances': deleted_instances,
                   'deleted_volumes': deleted_volumes,
                   'orphaned_connections': orphaned_connections})


def _generate_weekly_availability_report():
    try:
        availability = check_availability()
        mail_managers("Weekly Availability Report", availability)
    except Exception as e:
        logger.error(
            f"The Check_ResearchDesktop_Availability script returned: {e}.")


def vm_report_for_csv(reporting_months, operating_systems):
    now = datetime.now(utc)
    # A dict of zero values for the last year and this month so far
    date_list = [
        (offset_month_and_year(month_offset, now.month, now.year), 0)
        for month_offset in range(reporting_months, 0, -1)]
    start_date = datetime(day=1, month=date_list[0][0][0],
                          year=date_list[0][0][1], tzinfo=utc)
    empty_date_dict = dict(date_list)
    results = []

    # table of peak number of simultaneous vms of each OS
    data_lists = [
        [operating_system, empty_date_dict.copy()]
        for operating_system in operating_systems]
    for operating_system, instance_count in data_lists:
        date_counts = _get_vm_info(operating_system)['vm_count']
        for date_count in date_counts:
            date_count["simple_date"] = (
                date_count["date"].month, date_count["date"].year)
        for date in instance_count:
            date_counts_from_this_month = [
                date_count["count"] for date_count in date_counts
                if date_count["simple_date"] == date]
            if date_counts_from_this_month:
                instance_count[date] = max(date_counts_from_this_month)
    results.append({"name": "Peak VMs per month", "values": data_lists})

    # table of number of resizes per month
    data_lists = [
        [operating_system, empty_date_dict.copy()]
        for operating_system in operating_systems]
    for operating_system, resize_count in data_lists:
        resizes = Resize.objects.filter(
            instance__boot_volume__operating_system=operating_system,
            requested__gte=start_date)
        for resize in resizes:
            resize.start = (resize.requested.month
                            + 12 * resize.requested.year)
            if resize.expired():
                resize.end = resize.expired()
            else:
                resize.end = datetime.now(utc)
            resize.end = resize.end.month + 12 * resize.end.year
        for (month, year) in resize_count.keys():
            resize_count_month = month + 12 * year
            for resize in resizes:
                if resize.start <= resize_count_month <= resize.end:
                    resize_count[(month, year)] += 1
    results.append({"name": "Boosts", "values": data_lists})
    return results


def vm_report_for_page(operating_system):
    vm_count = Instance.objects.filter(
        deleted=None,
        boot_volume__operating_system=operating_system).count()
    vm_info = _get_vm_info(operating_system)
    return {'vm_count': {operating_system: vm_count},
            'vm_info': {operating_system: vm_info}}


def _get_vm_info(operating_system):
    vms = Instance.objects.filter(
        boot_volume__operating_system=operating_system).order_by('created')
    error_dates = vms.filter(error_flag__isnull=False) \
                     .order_by('error_flag') \
                     .annotate(date=TruncDay('error_flag', tzinfo=utc)) \
                     .values('date') \
                     .annotate(errored_count=Count('id')) \
                     .order_by('date')

    deleted = [
        {'date': vm.deleted, 'count': -1}
        for vm in vms.order_by('deleted') if vm.deleted]
    created = [{'date': vm.created, 'count': 1} for vm in vms]
    # `sorted` uses timsort, which means that for sorting two concatenated
    # sorted lists, it actually just merges the two lists in O(n)
    vm_count = sorted(created + deleted, key=itemgetter('date'))
    count = 0
    for date_obj in vm_count:
        count += date_obj['count']
        date_obj['count'] = count

    resizes = Resize.objects.filter(
        instance__boot_volume__operating_system=operating_system)
    resize_list = [
        resize.expired() for resize in resizes if resize.expired()]
    downsized = [
        {'date': expiry, 'count': -1} for expiry in sorted(resize_list)]
    supersized = [
        {'date': resize.requested, 'count': 1} for resize in resizes]
    resize_count = sorted(downsized + supersized, key=itemgetter('date'))
    count = 0
    for date_obj in resize_count:
        count += date_obj['count']
        date_obj['count'] = count

    return {'vm_count': vm_count,
            'error_dates': error_dates,
            'resizes': resize_count}
