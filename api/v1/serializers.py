from rest_framework import serializers

from researcher_workspace.models import User
from vm_manager.constants import NO_VM
from vm_manager.models import VMStatus


class UserSerializer(serializers.ModelSerializer):
    groups = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field='name')

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'sub',
                  'is_staff', 'is_superuser', 'is_active',
                  'date_joined', 'last_login',
                  'terms_version', 'date_agreed_terms', 'groups')


class UserDetailSerializer(UserSerializer):
    desktops = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ('desktops',)

    def get_desktops(self, user):
        """Summarise the user's current desktops from the database.

        Reports the latest VMStatus for each desktop type the user has
        launched, skipping desktops that no longer exist.  The status
        field is the source of truth: a shelved desktop's instance is
        deleted but the desktop still exists.  This deliberately
        avoids Instance.get_status() which makes a live Nova API call.
        """
        desktops = []
        seen = set()
        vm_statuses = (VMStatus.objects.filter(user=user)
                       .select_related('instance')
                       .order_by('-created'))
        for vm_status in vm_statuses:
            key = (vm_status.operating_system,
                   vm_status.requesting_feature_id)
            if key in seen:
                continue
            seen.add(key)
            if vm_status.status == NO_VM:
                continue
            desktops.append({
                'desktop_type': vm_status.operating_system,
                'status': vm_status.status,
                'instance_id': (str(vm_status.instance.id)
                                if vm_status.instance else None),
                'created': vm_status.created,
            })
        return desktops


class DesktopSerializer(serializers.ModelSerializer):
    """A user's current desktop, represented by its latest VMStatus."""

    user = serializers.CharField(source='user.username')
    desktop_type = serializers.CharField(source='operating_system')
    instance_id = serializers.SerializerMethodField()
    zone = serializers.SerializerMethodField()

    class Meta:
        model = VMStatus
        fields = ('id', 'user', 'desktop_type', 'status', 'zone',
                  'instance_id', 'created')

    def get_instance_id(self, vm_status):
        return (str(vm_status.instance.id)
                if vm_status.instance else None)

    def get_zone(self, vm_status):
        instance = vm_status.instance
        if instance and instance.boot_volume:
            return instance.boot_volume.zone
        return None
