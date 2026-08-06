from django.db.models import OuterRef, Subquery

from rest_framework import viewsets

from api.v1 import filters
from api.v1 import serializers
from researcher_workspace.models import User
from vm_manager.constants import NO_VM
from vm_manager.models import Instance, Resize, Volume, VMStatus


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only access to user accounts.  Staff only."""

    queryset = (User.objects.all()
                .prefetch_related('groups')
                .order_by('username'))
    lookup_field = 'username'
    # Usernames are email addresses, which may contain '.', '@', '+'
    # and '-'.  DRF's default lookup regex '[^/.]+' would reject any
    # username containing a dot.
    lookup_value_regex = '[^/]+'
    filterset_fields = {
        'is_staff': ['exact'],
        'is_superuser': ['exact'],
        'is_active': ['exact'],
        'terms_version': ['exact'],
        # Range filtering, e.g. ?last_login__gte=2026-01-01 to select
        # recently active users
        'last_login': ['gte', 'lte', 'isnull'],
        'date_joined': ['gte', 'lte'],
    }
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'date_joined', 'last_login']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return serializers.UserDetailSerializer
        return serializers.UserSerializer


class DesktopViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only access to users' current desktops.  Staff only.

    A desktop is the latest state record (VMStatus) for each user and
    desktop type, excluding desktops that no longer exist.  Status
    values are those in vm_manager.constants, e.g. VM_Okay,
    VM_Shelved, VM_Supersized, VM_Waiting, VM_Error.  Example:
    which users have a neurodesktop shelved:
    /api/v1/desktops/?desktop_type=neurodesktop&status=VM_Shelved
    """

    serializer_class = serializers.DesktopSerializer
    filterset_class = filters.DesktopFilter
    ordering_fields = ['created', 'user__username', 'operating_system',
                       'status']

    def get_queryset(self):
        latest = VMStatus.objects.filter(
            user=OuterRef('user'),
            operating_system=OuterRef('operating_system'),
            requesting_feature=OuterRef('requesting_feature'),
        ).order_by('-created')
        return (VMStatus.objects
                .filter(pk=Subquery(latest.values('pk')[:1]))
                .exclude(status=NO_VM)
                .select_related('user', 'instance__boot_volume')
                .order_by('-created'))


class VolumeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only access to Volume records.  Staff only.

    A Volume row tracks the Cinder boot volume holding all of a
    desktop's user data; its id IS the Cinder volume UUID.  Rows are
    kept when a desktop is deleted ('deleted' is set instead), so
    this is the full history.  Example - current error records:
    /api/v1/volumes/?error=true&deleted=false
    """

    queryset = (Volume.objects.all()
                .select_related('user', 'expiration', 'backup_expiration')
                .order_by('-created'))
    serializer_class = serializers.VolumeSerializer
    filterset_class = filters.VolumeFilter
    ordering_fields = ['created', 'user__username', 'zone', 'error_flag']


class InstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only access to Instance records.  Staff only.

    An Instance row tracks a Nova server; its id IS the Nova server
    UUID.  Rows are kept when the server is deleted ('deleted' is set
    instead), so this is the full history.  Example - current error
    records: /api/v1/instances/?error=true&deleted=false
    """

    queryset = (Instance.objects.all()
                .select_related('user', 'boot_volume', 'expiration')
                .order_by('-created'))
    serializer_class = serializers.InstanceSerializer
    filterset_class = filters.InstanceFilter
    ordering_fields = ['created', 'user__username', 'error_flag']


class VMStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only access to the VMStatus history.  Staff only.

    Every workflow state ever recorded, newest first - unlike
    /desktops/, which reports only the latest per user and desktop
    type.  Example - a desktop's workflow history:
    /api/v1/vmstatuses/?instance=<uuid>
    """

    queryset = (VMStatus.objects.all()
                .select_related('user', 'instance')
                .order_by('-created'))
    serializer_class = serializers.VMStatusSerializer
    filterset_class = filters.VMStatusFilter
    ordering_fields = ['created', 'user__username', 'status']


class ResizeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only access to Resize (boost) records.  Staff only.

    Example - unreverted resizes (candidates for manual cleanup after
    a failed downsize or delete):  /api/v1/resizes/?reverted=false
    """

    queryset = (Resize.objects.all()
                .select_related('instance', 'expiration')
                .order_by('-requested'))
    serializer_class = serializers.ResizeSerializer
    filterset_class = filters.ResizeFilter
    ordering_fields = ['requested', 'reverted']
