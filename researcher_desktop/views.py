import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.urls import reverse

from researcher_workspace.models import Feature
from researcher_desktop.constants import NOTIFY_VM_PATH_PLACEHOLDER
from researcher_desktop.utils.user_data_ubuntu import user_data_ubuntu
from researcher_desktop.utils.user_data_windows import user_data_windows
from researcher_desktop.utils.utils import get_vm_info
from researcher_desktop.utils.utils import desktop_type_names
from vm_manager import views as vm_man_views
from researcher_workspace.utils import not_support_staff, redirect_home
from vm_manager.constants import LINUX, REBOOT_BUTTON, SHELVE_BUTTON, DELETE_BUTTON, BOOST_BUTTON

logger = logging.getLogger(__name__)


def render_modules(request):
    researcher_desktop_vm_info = get_vm_info()
    feature_modules = []
    feature_scripts = []
    for desktop_type in desktop_type_names():
        feature_module, feature_script = vm_man_views.render_vm(
            request, request.user, desktop_type,
            researcher_desktop_vm_info.FEATURE,
            [REBOOT_BUTTON, SHELVE_BUTTON, DELETE_BUTTON, BOOST_BUTTON])
        feature_modules.append(feature_module)
        feature_scripts.append(feature_script)
    return feature_modules, feature_scripts

@login_required(login_url='login')
@user_passes_test(test_func=not_support_staff, login_url='staff_home', redirect_field_name=None)  # Only need to stop support staff creating vms, as they can't use any other function if they don't have a vm
def launch_vm(request, operating_system):
    if operating_system not in desktop_type_names():
        logger.error(f"Unrecognised operating system ({operating_system}) was requested by {request.user}")
        raise Http404

    vm_info = {}
    researcher_desktop_vm_info = get_vm_info()
    vm_info['flavor'] = researcher_desktop_vm_info.DEFAULT_FLAVOR
    vm_info['source_volume'] = researcher_desktop_vm_info.SOURCE_VOLUME[operating_system]
    vm_info['operating_system'] = operating_system
    vm_info['user_data_script'] = user_data_ubuntu\
                .replace(NOTIFY_VM_PATH_PLACEHOLDER, reverse('researcher_desktop:notify_vm'))
    vm_info['security_groups'] = settings.OS_SECGROUPS
    logger.info(request.user) 
    vm_man_views.launch_vm(request.user, vm_info, researcher_desktop_vm_info.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def delete_vm(request, vm_id):
    researcher_desktop_vm_info = get_vm_info()
    vm_man_views.delete_vm(request.user, vm_id, researcher_desktop_vm_info.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def shelve_vm(request, vm_id):
    researcher_desktop_vm_info = get_vm_info()
    vm_man_views.shelve_vm(request.user, vm_id, researcher_desktop_vm_info.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def unshelve_vm(request, operating_system):
    if operating_system not in desktop_type_names():
        logger.error(f"Unrecognised operating system ({operating_system}) was requested by {request.user}")
        raise Http404

    vm_info = {}
    researcher_desktop_vm_info = get_vm_info()
    vm_info['flavor'] = researcher_desktop_vm_info.DEFAULT_FLAVOR
    vm_info['source_volume'] = researcher_desktop_vm_info.SOURCE_VOLUME[operating_system]
    vm_info['operating_system'] = operating_system
    vm_info['user_data_script'] = ""
    vm_info['security_groups'] = settings.OS_SECGROUPS
    vm_man_views.unshelve_vm(request.user, vm_info, researcher_desktop_vm_info.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def reboot_vm(request, vm_id, reboot_level):
    researcher_desktop_vm_info = get_vm_info()
    vm_man_views.reboot_vm(request.user, vm_id, reboot_level, researcher_desktop_vm_info.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def get_rdp_file(request, vm_id):
    researcher_desktop_vm_info = get_vm_info()
    rdp_file = vm_man_views.get_rdp_file(request.user, vm_id, researcher_desktop_vm_info.FEATURE)
    response = HttpResponse(rdp_file, content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename="research_desktop.rdp"'
    return response


@login_required(login_url='login')
def supersize_vm(request, vm_id):
    researcher_desktop_vm_info = get_vm_info()
    vm_man_views.supersize_vm(request.user, vm_id, researcher_desktop_vm_info.BIG_FLAVOR, researcher_desktop_vm_info.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def downsize_vm(request, vm_id):
    researcher_desktop_vm_info = get_vm_info()
    vm_man_views.downsize_vm(request.user, vm_id, researcher_desktop_vm_info.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def extend(request, vm_id):
    researcher_desktop_vm_info = get_vm_info()
    vm_man_views.extend(request.user, vm_id, researcher_desktop_vm_info.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def start_downsizing_cron_job(request):
    if not request.user.is_superuser:
        raise Http404()
    researcher_desktop_vm_info = get_vm_info()
    return HttpResponse(vm_man_views.start_downsizing_cron_job(researcher_desktop_vm_info.FEATURE), content_type='text/plain')


def notify_vm(request):
    researcher_desktop_vm_info = get_vm_info()
    return HttpResponse(vm_man_views.notify_vm(request, researcher_desktop_vm_info.FEATURE))


def rd_report(reporting_months):
    return vm_man_views.vm_report_for_csv(reporting_months,
                                          desktop_type_names())


def rd_report_page():
    rd_report_page_info = {'vm_count': {}, 'vm_info': {}}
    for operating_system in desktop_type_names():
        operating_system_info = vm_man_views.vm_report_for_page(operating_system)
        rd_report_page_info['vm_count'].update(operating_system_info['vm_count'])
        rd_report_page_info['vm_info'].update(operating_system_info['vm_info'])
    return rd_report_page_info


def rd_report_for_user(user):
    researcher_desktop_vm_info = get_vm_info()
    return vm_man_views.rd_report_for_user(user, desktop_type_names(),
                                           researcher_desktop_vm_info.FEATURE)
