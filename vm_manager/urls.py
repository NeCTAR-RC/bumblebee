from django.urls import path

from . import views

app_name = 'vm_manager'

urlpatterns = [
    path('admin_delete_vm/<uuid:vm_id>',
         views.admin_delete_vm, name='admin_delete_vm'),
    # path('test_function/', views.test_function, name='test_function'),
    path('db_check/', views.database_check, name='db_check'),
]
