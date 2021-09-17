import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect, Http404
from django.urls import reverse

from researcher_workspace.models import Feature
from researcher_desktop.constants import NOTIFY_VM_PATH_PLACEHOLDER
from researcher_desktop.utils.user_data_ubuntu import user_data_ubuntu
from researcher_desktop.utils.utils import get_vm_info
from researcher_desktop.utils.utils import get_desktop_types
from vm_manager import views as vm_man_views
from researcher_workspace.utils import not_support_staff, redirect_home
from vm_manager.constants import LINUX, REBOOT_BUTTON, SHELVE_BUTTON, DELETE_BUTTON, BOOST_BUTTON

logger = logging.getLogger(__name__)


def render_modules(request):
    catalog = get_vm_info()
    feature_modules = []
    feature_scripts = []
    for desktop_type in get_desktop_types():
        feature_module, feature_script = vm_man_views.render_vm(
            request, request.user, desktop_type,
            catalog.FEATURE,
            [REBOOT_BUTTON, SHELVE_BUTTON, DELETE_BUTTON, BOOST_BUTTON])
        feature_modules.append(feature_module)
        feature_scripts.append(feature_script)
    return feature_modules, feature_scripts

@login_required(login_url='login')
@user_passes_test(test_func=not_support_staff, login_url='staff_home', redirect_field_name=None)  # Only need to stop support staff creating vms, as they can't use any other function if they don't have a vm
def launch_vm(request, desktop):
    desktop_type_ids = [d.id for d in get_desktop_types()]
    if desktop not in desktop_type_ids:
        logger.error(f"Unrecognised desktop ({desktop}) was requested by {request.user}")
        raise Http404

    vm_info = {}
    catalog = get_vm_info()
    vm_info['flavor'] = catalog.DESKTOPS[desktop]['default_flavor']
    vm_info['source_volume'] = catalog.DESKTOPS[desktop]['source_volume']
    vm_info['operating_system'] = desktop
    vm_info['user_data_script'] = user_data_ubuntu\
                .replace(NOTIFY_VM_PATH_PLACEHOLDER,
                         reverse('researcher_desktop:notify_vm'))
    vm_info['security_groups'] = settings.OS_SECGROUPS
    logger.info(request.user) 
    vm_man_views.launch_vm(request.user, vm_info, catalog.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def delete_vm(request, vm_id):
    catalog = get_vm_info()
    vm_man_views.delete_vm(request.user, vm_id, catalog.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def shelve_vm(request, vm_id):
    catalog = get_vm_info()
    vm_man_views.shelve_vm(request.user, vm_id, catalog.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def unshelve_vm(request, desktop):
    if desktop not in desktop_type_ids():
        logger.error(f"Unrecognised desktop ({desktop}) was requested by {request.user}")
        raise Http404

    vm_info = {}
    catalog = get_vm_info()
    vm_info['flavor'] = catalog.DESKTOPS[desktop]['default_flavor']
    vm_info['source_volume'] = catalog.DESKTOPS[desktop]['source_volume']
    vm_info['operating_system'] = desktop
    vm_info['user_data_script'] = ""
    vm_info['security_groups'] = settings.OS_SECGROUPS
    vm_man_views.unshelve_vm(request.user, vm_info, catalog.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def reboot_vm(request, vm_id, reboot_level):
    catalog = get_vm_info()
    vm_man_views.reboot_vm(request.user, vm_id, reboot_level, catalog.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def get_rdp_file(request, vm_id):
    catalog = get_vm_info()
    rdp_file = vm_man_views.get_rdp_file(request.user, vm_id, catalog.FEATURE)
    response = HttpResponse(rdp_file, content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename="research_desktop.rdp"'
    return response


@login_required(login_url='login')
def supersize_vm(request, vm_id):
    catalog = get_vm_info()
    # FIX ME: need to know what the current desktop type is
    vm_man_views.supersize_vm(request.user, vm_id, catalog.BIG_FLAVOR,
                              catalog.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def downsize_vm(request, vm_id):
    catalog = get_vm_info()
    # FIX ME: need to know what the current desktop type is(?)
    vm_man_views.downsize_vm(request.user, vm_id, catalog.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def extend(request, vm_id):
    catalog = get_vm_info()
    vm_man_views.extend(request.user, vm_id, catalog.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def start_downsizing_cron_job(request):
    if not request.user.is_superuser:
        raise Http404()
    catalog = get_vm_info()
    return HttpResponse(
        vm_man_views.start_downsizing_cron_job(catalog.FEATURE),
        content_type='text/plain')


def notify_vm(request):
    catalog = get_vm_info()
    return HttpResponse(vm_man_views.notify_vm(request, catalog.FEATURE))


@login_required(login_url='login')
def status_vm(request, desktop):
    catalog = get_vm_info()
    state, what_to_show, vm_id = vm_man_views.get_vm_state(request.user, desktop, catalog.FEATURE)
    result = {'state': state, 'status': what_to_show}
    return JsonResponse(result)


def rd_report(reporting_months):
    return vm_man_views.vm_report_for_csv(reporting_months,
                                          desktop_type_ids())


def rd_report_page():
    rd_report_page_info = {'vm_count': {}, 'vm_info': {}}
    for desktop in desktop_type_ids():
        desktop_info = vm_man_views.vm_report_for_page(desktop)
        rd_report_page_info['vm_count'].update(desktop_info['vm_count'])
        rd_report_page_info['vm_info'].update(desktop_info['vm_info'])
    return rd_report_page_info


def rd_report_for_user(user):
    catalog = get_vm_info()
    return vm_man_views.rd_report_for_user(user, desktop_type_names(),
                                           catalog.FEATURE)
