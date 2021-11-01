"""researcher_workspace URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.views.generic.base import RedirectView
from django.urls import path, re_path, include, reverse

from mozilla_django_oidc import views as oidc_views

from . import views

app_name = 'researcher_workspace'

urlpatterns = [
    path('', views.index, name='index'),
    path('home/', views.home, name='home'),
    path('rcsadmin/', admin.site.urls),
    path('vm_manager/', include('vm_manager.urls')),
    path('researcher_desktop/', include('researcher_desktop.urls')),
#    path('specialty_resources/', include('specialty_resources.urls')),
    path('desktop/<str:desktop_name>', views.desktop_details, name='desktop_details'),
    path('orion_report/', views.orion_report, name='orion_report'),
    path('desktop_description/', views.desktop_description, name='desktop_description'),
    path('terms/', views.terms, name='terms'),
    path('help/', views.help, name='help'),
    path('contact_us/', views.help, name='contact_us'),
    path('contact/', views.help, name='contact'),
    path('django-rq/', include('django_rq.urls')),
    path('request_feature_access/<str:feature_app_name>', views.request_feature_access, name='request_feature_access'),
    path('staff_home/', views.staff_home, name='staff_home'),
    path('user_search/', views.user_search, name='user_search'),
    path('user_search_details/<str:username>', views.user_search_details, name='user_search_details'),
    path('new_project', views.new_project, name='new_project'),
    path('projects', views.projects, name='projects'),
    path('project/<int:project_id>', views.project_edit, name='project_edit'),
    path('report/', views.report, name='report'),
    path('learn/', views.learn, name='learn'),
    # OIDC auth
    path('oidc/', include('mozilla_django_oidc.urls')),
    path('login/', oidc_views.OIDCAuthenticationRequestView.as_view(), name='login'),
]

handler404 = views.custom_page_not_found
handler500 = views.custom_page_error

admin.site.site_header = "Researcher Workspace Admin"
admin.site.site_title = "Researcher Workspace Admin Portal"
admin.site.index_title = "Welcome to the Researcher Workspace Admin Portal"
