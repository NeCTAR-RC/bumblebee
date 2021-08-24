from uuid import UUID

import django_rq
import logging

from datetime import datetime, timezone, timedelta
from django.core.mail import mail_managers
from django.db.models import Count
from django.db.models.functions import TruncDay
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render
from operator import itemgetter

from vm_manager.constants import LINUX, WINDOWS  # ToDo: Maybe this should be removed and the reporting be refactored
from researcher_workspace.utils import offset_month_and_year
from vm_manager.models import Instance, Resize, Volume
from vm_manager.utils.utils import get_nectar
from vm_manager.vm_functions.resize_vm import downsize_expired_supersized_vms
from vm_manager.utils.Check_ResearchDesktop_Availability import check_availability

logger = logging.getLogger(__name__)


def test_function(request):
    if not request.user.is_superuser:
        raise Http404()
    return HttpResponse(_generate_weekly_availability_report(), content_type='text/plain')


def admin_worker(request):
    if not request.user.is_superuser:
        raise Http404()
    return HttpResponse("do something", content_type='text/plain')


def db_check(request):
    if not request.user.is_superuser:
        raise Http404()
    n = get_nectar()
    nova_servers = n.nova.servers.list()
    cinder_volumes = n.cinder.volumes.list()

    db_deleted_instances = Instance.objects.exclude(deleted=None).values_list('id', flat=True)
    deleted_instances = [(server.id, server.name, server.metadata['environment'] if 'environment' in server.metadata else '') for server in nova_servers if UUID(server.id) in db_deleted_instances]

    db_deleted_volumes = Volume.objects.exclude(deleted=None).values_list('id', flat=True)
    deleted_volumes = [(volume.id, volume.name, volume.metadata['environment'] if 'environment' in volume.metadata else volume.name[-1]) for volume in cinder_volumes if UUID(volume.id) in db_deleted_volumes]

    db_instances = Instance.objects.filter(deleted=None).values_list('id', flat=True)
    missing_instances = [(server.id, server.name, server.metadata['environment'] if 'environment' in server.metadata else '') for server in nova_servers if UUID(server.id) not in db_instances]

    db_volumes = Volume.objects.filter(deleted=None).values_list('id', flat=True)
    missing_volumes = [(volume.id, volume.name, volume.metadata['environment'] if 'environment' in volume.metadata else volume.name[-1]) for volume in cinder_volumes if UUID(volume.id) not in db_volumes]

    return render(request, 'vm_manager/db_check.html', {'missing_instances': missing_instances, 'missing_volumes': missing_volumes, 'deleted_instances': deleted_instances, 'deleted_volumes': deleted_volumes, })


def start_downsizing_cron_job(requesting_feature):
    scheduler = django_rq.get_scheduler('default')
    # Uncomment this line temporarily to activate this function
    """scheduler.cron("59 13 * * *", downsize_expired_supersized_vms, requesting_feature)"""
    # Set cron job to 13:59 UTC as the server runs on UTC
    # and that translates to 23:59 AEST or 0:59 AEDT (during daylight savings)
    return scheduler.get_jobs(with_times=True)


def _generate_weekly_availability_report():
    try:
        availability = check_availability()
        mail_managers("Weekly Availability Report", availability)
    except Exception as e:
        logger.error(
            f"The Check_ResearchDesktop_Availability script returned: {e}.")


def vm_report_for_csv(reporting_months, operating_systems):
    now = datetime.now(timezone.utc)
    # A dict of zero values for the last year and this month so far
    date_list = [(offset_month_and_year(month_offset, now.month, now.year), 0) for month_offset in
                 range(reporting_months, 0, -1)]
    start_date = datetime(day=1, month=date_list[0][0][0], year=date_list[0][0][1], tzinfo=timezone.utc)
    empty_date_dict = dict(date_list)
    results = []

    # table of peak number of simultaneous vms of each OS
    data_lists = [[operating_system, empty_date_dict.copy()] for operating_system in operating_systems]
    for operating_system, instance_count in data_lists:
        date_counts = _get_vm_info(operating_system)['vm_count']
        for date_count in date_counts:
            date_count["simple_date"] = (date_count["date"].month, date_count["date"].year)
        for date in instance_count:
            date_counts_from_this_month = [date_count["count"] for date_count in date_counts
                                           if date_count["simple_date"] == date]
            if date_counts_from_this_month:
                instance_count[date] = max(date_counts_from_this_month)
    results.append({"name": "Peak VMs per month", "values": data_lists})

    # table of number of resizes per month
    data_lists = [[operating_system, empty_date_dict.copy()] for operating_system in operating_systems]
    for operating_system, resize_count in data_lists:
        resizes = Resize.objects.filter(instance__boot_volume__operating_system=operating_system,
                                        requested__gte=start_date)
        for resize in resizes:
            resize.start = resize.requested.month + 12 * resize.requested.year
            if resize.expired():
                resize.end = resize.expired()
            else:
                resize.end = datetime.now(timezone.utc)
            resize.end = resize.end.month + 12 * resize.end.year
        for (month, year) in resize_count.keys():
            resize_count_month = month + 12 * year
            for resize in resizes:
                if resize.start <= resize_count_month <= resize.end:
                    resize_count[(month, year)] += 1
    results.append({"name": "Boosts", "values": data_lists})
    return results


def vm_report_for_page(operating_system):
    vm_count = Instance.objects.filter(deleted=None, boot_volume__operating_system=operating_system).count()
    vm_info = _get_vm_info(operating_system)
    return {'vm_count': {operating_system: vm_count},
            'vm_info': {operating_system: vm_info}}


def _get_vm_info(operating_system):
    vms = Instance.objects.filter(boot_volume__operating_system=operating_system).order_by('created')

    error_dates = vms.filter(error_flag__isnull=False).order_by('error_flag') \
        .annotate(date=TruncDay('error_flag')).values('date') \
        .annotate(errored_count=Count('id')) \
        .order_by('date')

    deleted = [{'date': vm.deleted, 'count': -1} for vm in vms.order_by('deleted') if vm.deleted]
    created = [{'date': vm.created, 'count': 1} for vm in vms]
    # `sorted` uses timsort, which means that for sorting two concatenated sorted lists,
    # it actually just merges the two lists with complexity O(n)
    vm_count = sorted(created + deleted, key=itemgetter('date'))
    count = 0
    for date_obj in vm_count:
        count += date_obj['count']
        date_obj['count'] = count

    resizes = Resize.objects.filter(instance__boot_volume__operating_system=operating_system)
    resize_list = [resize.expired() for resize in resizes if resize.expired()]
    downsized = [{'date': expiry, 'count': -1} for expiry in sorted(resize_list)]
    supersized = [{'date': resize.requested, 'count': 1} for resize in resizes]
    resize_count = sorted(downsized + supersized, key=itemgetter('date'))
    count = 0
    for date_obj in resize_count:
        count += date_obj['count']
        date_obj['count'] = count

    return {'vm_count': vm_count, 'error_dates': error_dates, 'resizes': resize_count}
