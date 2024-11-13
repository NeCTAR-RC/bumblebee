import logging

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from researcher_desktop.utils.utils import get_desktop_type, \
    get_best_zone, desktop_types, desktops_feature

from vm_manager import views as vm_man_views
from researcher_workspace.utils import not_support_staff, redirect_home, \
    agreed_to_terms
from vm_manager.constants import REBOOT_BUTTON, SHELVE_BUTTON, \
    DELETE_BUTTON, BOOST_BUTTON, DOWNSIZE_BUTTON, EXTEND_BUTTON, \
    EXTEND_BOOST_BUTTON, UNSHELVE_BUTTON

logger = logging.getLogger(__name__)


def render_modules(request):
    modules = []
    for dt in desktop_types():
        buttons = [REBOOT_BUTTON, SHELVE_BUTTON, DELETE_BUTTON,
                   EXTEND_BUTTON, UNSHELVE_BUTTON]
        # If desktop is resizable, include the boost-related buttons
        if dt.is_resizable:
            buttons = buttons + [BOOST_BUTTON,
                   DOWNSIZE_BUTTON, EXTEND_BOOST_BUTTON]
        modules.append(
            vm_man_views.render_vm(request, request.user, dt, buttons)
        )
    return modules


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
@user_passes_test(test_func=not_support_staff, login_url='staff_home',
                  redirect_field_name=None)
def launch_vm(request, desktop, zone_name=None):
    desktop_type = get_desktop_type(desktop)
    zone = get_best_zone(request.user.email, desktop_type,
                         chosen_zone=zone_name)
    vm_man_views.launch_vm(request.user, desktop_type, zone)
    return redirect_home(request)


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def delete_vm(request, vm_id):
    vm_man_views.delete_vm(request.user, vm_id, desktops_feature())
    return redirect_home(request)


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def shelve_vm(request, vm_id):
    vm_man_views.shelve_vm(request.user, vm_id, desktops_feature())
    return redirect_home(request)


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def unshelve_vm(request, desktop):
    vm_man_views.unshelve_vm(request.user, get_desktop_type(desktop))
    return redirect_home(request)


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def delete_shelved_vm(request, desktop):
    vm_man_views.delete_shelved_vm(request.user, get_desktop_type(desktop))
    return redirect_home(request)


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def reboot_vm(request, vm_id, reboot_level):
    vm_man_views.reboot_vm(request.user, vm_id,
                           reboot_level, desktops_feature())
    return redirect_home(request)


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def get_rdp_file(request, vm_id):
    rdp_file = vm_man_views.get_rdp_file(request.user, vm_id,
                                         desktops_feature())
    response = HttpResponse(rdp_file, content_type='text/plain')
    response['Content-Disposition'] = \
        'attachment; filename="research_desktop.rdp"'
    return response


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def supersize_vm(request, vm_id):
    vm_man_views.supersize_vm(request.user, vm_id, desktops_feature())
    return redirect_home(request)


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def downsize_vm(request, vm_id):
    vm_man_views.downsize_vm(request.user, vm_id, desktops_feature())
    return redirect_home(request)


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def extend(request, vm_id):
    vm_man_views.extend_vm(request.user, vm_id, desktops_feature())
    return redirect_home(request)


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def extend_boost(request, vm_id):
    vm_man_views.extend_boost_vm(request.user, vm_id, desktops_feature())
    return redirect_home(request)


def notify_vm(request):
    return HttpResponse(vm_man_views.notify_vm(request, desktops_feature()))


@csrf_exempt
def phone_home(request):
    return HttpResponse(vm_man_views.phone_home(request, desktops_feature()))


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def status_vm(request, desktop):
    desktop_type = get_desktop_type(desktop)
    result = vm_man_views.get_vm_status(request.user, desktop_type)
    return JsonResponse(result)


def rd_report(reporting_months):
    return vm_man_views.vm_report_for_csv(reporting_months, desktop_types())


def rd_report_page():
    rd_report_page_info = {'vm_count': {}, 'vm_info': {},
                           'desktop_types': desktop_types()}
    for desktop in desktop_types():
        desktop_info = vm_man_views.vm_report_for_page(desktop)
        rd_report_page_info['vm_count'].update(desktop_info['vm_count'])
        rd_report_page_info['vm_info'].update(desktop_info['vm_info'])
    return rd_report_page_info


def rd_report_for_user(user):
    return vm_man_views.rd_report_for_user(user, desktop_types(),
                                           desktops_feature())
