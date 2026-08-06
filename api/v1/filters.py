from django_filters import rest_framework as filters

from vm_manager.models import Instance, Resize, Volume, VMStatus


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


# The timestamp fields on cloud resources (error_flag, deleted,
# marked_for_deletion, shelved_at, reverted) act as flags: set means
# the thing happened.  The boolean filters below expose them as flags
# (?error=true means 'has an error'); exclude=True inverts the isnull
# lookup to give the natural sense.

class VolumeFilter(filters.FilterSet):
    user = filters.CharFilter(field_name='user__username')
    desktop_type = filters.CharFilter(field_name='operating_system')
    error = filters.BooleanFilter(
        field_name='error_flag', lookup_expr='isnull', exclude=True)
    deleted = filters.BooleanFilter(
        field_name='deleted', lookup_expr='isnull', exclude=True)
    marked_for_deletion = filters.BooleanFilter(
        field_name='marked_for_deletion', lookup_expr='isnull',
        exclude=True)
    shelved = filters.BooleanFilter(
        field_name='shelved_at', lookup_expr='isnull', exclude=True)
    created = filters.IsoDateTimeFromToRangeFilter()

    class Meta:
        model = Volume
        fields = ['user', 'desktop_type', 'zone', 'hostname_id', 'error',
                  'deleted', 'marked_for_deletion', 'shelved', 'created']


class InstanceFilter(filters.FilterSet):
    user = filters.CharFilter(field_name='user__username')
    volume = filters.CharFilter(field_name='boot_volume__id')
    error = filters.BooleanFilter(
        field_name='error_flag', lookup_expr='isnull', exclude=True)
    deleted = filters.BooleanFilter(
        field_name='deleted', lookup_expr='isnull', exclude=True)
    marked_for_deletion = filters.BooleanFilter(
        field_name='marked_for_deletion', lookup_expr='isnull',
        exclude=True)
    created = filters.IsoDateTimeFromToRangeFilter()

    class Meta:
        model = Instance
        fields = ['user', 'volume', 'ip_address', 'error', 'deleted',
                  'marked_for_deletion', 'created']


class VMStatusFilter(filters.FilterSet):
    user = filters.CharFilter(field_name='user__username')
    desktop_type = filters.CharFilter(field_name='operating_system')
    instance = filters.CharFilter(field_name='instance__id')
    created = filters.IsoDateTimeFromToRangeFilter()

    class Meta:
        model = VMStatus
        fields = ['user', 'desktop_type', 'status', 'instance', 'created']


class ResizeFilter(filters.FilterSet):
    user = filters.CharFilter(field_name='instance__user__username')
    instance = filters.CharFilter(field_name='instance__id')
    reverted = filters.BooleanFilter(
        field_name='reverted', lookup_expr='isnull', exclude=True)
    requested = filters.IsoDateTimeFromToRangeFilter()

    class Meta:
        model = Resize
        fields = ['user', 'instance', 'reverted', 'requested']
