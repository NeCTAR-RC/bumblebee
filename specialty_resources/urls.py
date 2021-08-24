from django.urls import path

from . import views
from .constants import APP_NAME

app_name = APP_NAME

urlpatterns = [
    path('launch_vm/', views.launch_vm, name='launch_vm'),
    path('delete_vm/<uuid:vm_id>', views.delete_vm, name='delete_vm'),
    path('reboot_vm/<uuid:vm_id>/<str:reboot_level>', views.reboot_vm, name='reboot_vm'),
    path('get_rdp_file/<uuid:vm_id>', views.get_rdp_file, name='get_rdp_file'),
    path('notify_vm/', views.notify_vm, name='notify_vm'),
]
