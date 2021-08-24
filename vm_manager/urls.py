from django.urls import path

from . import views

app_name = 'vm_manager'

urlpatterns = [
    path('admin_delete_vm/<uuid:vm_id>', views.admin_delete_vm, name='admin_delete_vm'),
    path('test_function/', views.test_function, name='test_function'),
    path('admin_worker/', views.admin_worker, name='admin_worker'),
    path('db_check/', views.db_check, name='db_check'),
]
