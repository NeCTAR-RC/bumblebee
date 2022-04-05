from django.contrib import admin
from django.urls import path, include

from mozilla_django_oidc import views as oidc_views

from . import views

app_name = 'researcher_workspace'

urlpatterns = [
    path('', views.index, name='index'),
    path('', include('django_prometheus.urls')),
    path('home/', views.home, name='home'),
    path('vm_manager/', include('vm_manager.urls')),
    path('researcher_desktop/', include('researcher_desktop.urls')),
    path('desktop/<str:desktop_name>',
         views.desktop_details, name='desktop_details'),
    path('orion_report/', views.orion_report, name='orion_report'),
    path('about/', views.about, name='about'),
    path('terms/', views.terms, name='terms'),
    path('agree_terms/<int:version>', views.agree_terms, name='agree_terms'),
    path('help/', views.help, name='help'),
    path('contact_us/', views.help, name='contact_us'),
    path('contact/', views.help, name='contact'),
    path('django-rq/', include('django_rq.urls')),
    path('request_feature_access/<str:feature_app_name>',
         views.request_feature_access, name='request_feature_access'),
    path('staff_home/', views.staff_home, name='staff_home'),
    path('user_search/', views.user_search, name='user_search'),
    path('user_search_details/<str:username>',
         views.user_search_details, name='user_search_details'),
    path('new_project', views.new_project, name='new_project'),
    path('projects', views.projects, name='projects'),
    path('project/<int:project_id>', views.project_edit, name='project_edit'),
    path('profile/', views.profile, name='profile'),
    path('report/', views.report, name='report'),
    path('learn/', views.learn, name='learn'),
    path('login/fail/', views.login_fail, name='login_fail'),
    path('healthcheck/status', include('health_check.urls')),
    path('healthcheck/', views.healthcheck, name='healthcheck'),
    # OIDC auth
    path('oidc/', include('mozilla_django_oidc.urls')),
    path('login/',
         oidc_views.OIDCAuthenticationRequestView.as_view(), name='login'),
    # Bumblebee admin site uses regular login view
    path('rcsadmin/login/',
         oidc_views.OIDCAuthenticationRequestView.as_view()),
    path('rcsadmin/', admin.site.urls),
]

handler404 = views.custom_page_not_found
handler500 = views.custom_page_error

admin.site.site_header = "Researcher Workspace Admin"
admin.site.site_title = "Researcher Workspace Admin Portal"
admin.site.index_title = "Welcome to the Researcher Workspace Admin Portal"
