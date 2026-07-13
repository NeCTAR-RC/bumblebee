from django.db.models import OuterRef, Subquery

from rest_framework import viewsets

from api.v1 import filters
from api.v1 import serializers
from researcher_workspace.models import User
from vm_manager.constants import NO_VM
from vm_manager.models import VMStatus


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
