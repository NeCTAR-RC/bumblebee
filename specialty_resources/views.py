import logging
from datetime import datetime

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.template import loader
from django.urls import reverse

from researcher_desktop.utils.user_data_ubuntu import user_data_ubuntu
from researcher_desktop.utils.user_data_windows import user_data_windows
from researcher_workspace.settings import DEBUG
from specialty_resources.constants import IMAGE_NAME, NOTIFY_VM_PATH_PLACEHOLDER, BASIC_FLAVORS, OS_CHOICES
from specialty_resources.forms import SpecialtyResourcesCreationForm
from specialty_resources.utils.utils import get_vm_info
from vm_manager import views as vm_man_views
from researcher_workspace.utils import not_support_staff, redirect_home
from vm_manager.constants import LINUX, WINDOWS, DELETE_BUTTON, NO_VM, REBOOT_BUTTON
from vm_manager.models import VMStatus

logger = logging.getLogger(__name__)


def render_modules(request):
    specialty_resources_vm_info = get_vm_info()
    vm_status = None
    for operating_system in IMAGE_NAME.keys():
        new_vm_status = VMStatus.objects.get_latest_vm_status(request.user, operating_system, specialty_resources_vm_info.FEATURE)
        if new_vm_status and (not vm_status or new_vm_status.created > vm_status.created):
            vm_status = new_vm_status
    operating_system = vm_status.operating_system if vm_status else LINUX
    if not vm_status or vm_status.status == NO_VM:
        if DEBUG:
            print(f"[{datetime.now()}] DEBUG", vm_status)
        form = SpecialtyResourcesCreationForm(current_user=request.user)
        feature_module = loader.render_to_string(f'specialty_resources/No_VM.html',
                     {'form': form, 'requesting_feature': specialty_resources_vm_info.FEATURE, }, request)
        feature_script = ""
    else:
        feature_module, feature_script = vm_man_views.render_vm(request, request.user, operating_system, specialty_resources_vm_info.FEATURE,
                                                            [DELETE_BUTTON, REBOOT_BUTTON])
    feature_modules = [feature_module]
    feature_scripts = [feature_script]
    return feature_modules, feature_scripts


@login_required(login_url='login')
@user_passes_test(test_func=not_support_staff, login_url='staff_home', redirect_field_name=None)  # Only need to stop support staff creating vms, as they can't use any other function if they don't have a vm
def launch_vm(request):
    if request.method == 'POST':
        form = SpecialtyResourcesCreationForm(request.POST, current_user=request.user)

        if not form.is_valid():
            logger.error(f"Invalid form inputs {form.errors.as_data()} while launching Specialty Resources"
                         f" by {request.user}")
            raise Http404

        operating_system = form.cleaned_data['operating_system']
        flavor = form.cleaned_data['flavor']

        vm_info = {}
        specialty_resources_vm_info = get_vm_info()
        vm_info['flavor'] = specialty_resources_vm_info.FLAVORS[flavor]
        vm_info['source_volume'] = specialty_resources_vm_info.SOURCE_VOLUME[operating_system]
        vm_info['operating_system'] = operating_system
        if operating_system == LINUX:
            vm_info['user_data_script'] = user_data_ubuntu\
                    .replace(NOTIFY_VM_PATH_PLACEHOLDER, reverse('specialty_resources:notify_vm'))
            vm_info['security_groups'] = ['ssh-int', 'https-int', 'fastx', ]
        elif operating_system == WINDOWS:
            vm_info['user_data_script'] = user_data_windows\
                .replace(NOTIFY_VM_PATH_PLACEHOLDER, reverse('specialty_resources:notify_vm'))
            vm_info['security_groups'] = ['ssh-int', 'https-int', 'rdp-int']
        else:
            raise ArithmeticError  # code will never get here

        vm_man_views.launch_vm(request.user, vm_info, specialty_resources_vm_info.FEATURE)
    return HttpResponseRedirect(reverse('home'))


@login_required(login_url='login')
def delete_vm(request, vm_id):
    specialty_resources_vm_info = get_vm_info()
    vm_man_views.delete_vm(request.user, vm_id, specialty_resources_vm_info.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def reboot_vm(request, vm_id, reboot_level):
    specialty_resources_vm_info = get_vm_info()
    vm_man_views.reboot_vm(request.user, vm_id, reboot_level, specialty_resources_vm_info.FEATURE)
    return redirect_home(request)


@login_required(login_url='login')
def get_rdp_file(request, vm_id):
    specialty_resources_vm_info = get_vm_info()
    rdp_file = vm_man_views.get_rdp_file(request.user, vm_id, specialty_resources_vm_info.FEATURE)
    response = HttpResponse(rdp_file, content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename="specialty_resources.rdp"'
    return response


def notify_vm(request):
    specialty_resources_vm_info = get_vm_info()
    return HttpResponse(vm_man_views.notify_vm(request, specialty_resources_vm_info.FEATURE))
