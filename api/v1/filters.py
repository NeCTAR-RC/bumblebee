from django_filters import rest_framework as filters

from vm_manager.models import VMStatus


class DesktopFilter(filters.FilterSet):
    """Filters for the desktops endpoint.

    Filter names use the API's vocabulary (desktop_type, user, zone)
    rather than the underlying model field names.
    """

    desktop_type = filters.CharFilter(field_name='operating_system')
    user = filters.CharFilter(field_name='user__username')
    zone = filters.CharFilter(field_name='instance__boot_volume__zone')
    created = filters.IsoDateTimeFromToRangeFilter()

    class Meta:
        model = VMStatus
        fields = ['desktop_type', 'status', 'user', 'zone', 'created']
