from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework import routers

from api.v1 import views

router = routers.DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'desktops', views.DesktopViewSet, basename='desktop')
router.register(r'volumes', views.VolumeViewSet, basename='volume')
router.register(r'instances', views.InstanceViewSet, basename='instance')
router.register(r'vmstatuses', views.VMStatusViewSet,
                basename='vmstatus')
router.register(r'resizes', views.ResizeViewSet, basename='resize')

urlpatterns = [
    path('', include(router.urls)),
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('schema/swagger/',
         SpectacularSwaggerView.as_view(url_name='api:schema'),
         name='swagger'),
]
