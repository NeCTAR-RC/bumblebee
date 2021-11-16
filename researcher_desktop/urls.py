from django.urls import path

from . import views
from .constants import APP_NAME

app_name = APP_NAME

urlpatterns = [
    path('launch_vm/<str:desktop>/<str:zone_name>',
         views.launch_vm, name='launch_vm'),
    path('launch_vm/<str:desktop>/',
         views.launch_vm, name='launch_vm_default'),
    path('delete_vm/<uuid:vm_id>', views.delete_vm, name='delete_vm'),
    path('reboot_vm/<uuid:vm_id>/<str:reboot_level>',
         views.reboot_vm, name='reboot_vm'),
    path('shelve_vm/<uuid:vm_id>', views.shelve_vm, name='shelve_vm'),
    path('unshelve_vm/<str:desktop>', views.unshelve_vm, name='unshelve_vm'),
    path('supersize_vm/<uuid:vm_id>', views.supersize_vm, name='supersize_vm'),
    path('downsize_vm/<uuid:vm_id>', views.downsize_vm, name='downsize_vm'),
    path('extend/<uuid:vm_id>', views.extend, name='extend'),
    path('notify_vm/', views.notify_vm, name='notify_vm'),
    path('phone_home/', views.phone_home, name='phone_home'),
    path('status_vm/<str:desktop>', views.status_vm, name='status_vm'),
    path('start_downsizing_cron_job/',
         views.start_downsizing_cron_job, name='start_downsizing_cron_job'),
]
