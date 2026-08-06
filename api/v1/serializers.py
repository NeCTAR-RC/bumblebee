from rest_framework import serializers

from researcher_workspace.models import User
from vm_manager.constants import NO_VM
from vm_manager.models import Instance, Resize, Volume, VMStatus


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
    volume_id = serializers.SerializerMethodField()
    zone = serializers.SerializerMethodField()

    class Meta:
        model = VMStatus
        fields = ('id', 'user', 'desktop_type', 'status', 'zone',
                  'instance_id', 'volume_id', 'created')

    def get_instance_id(self, vm_status):
        return (str(vm_status.instance.id)
                if vm_status.instance else None)

    def get_volume_id(self, vm_status):
        instance = vm_status.instance
        if instance and instance.boot_volume:
            return str(instance.boot_volume.id)
        return None

    def get_zone(self, vm_status):
        instance = vm_status.instance
        if instance and instance.boot_volume:
            return instance.boot_volume.zone
        return None


class VolumeSerializer(serializers.ModelSerializer):
    """A Volume record.  Its id IS the Cinder volume UUID.

    The boot volume holds all of a desktop's user data, so this is
    the record that matters for data-safety decisions.  Note that
    error_flag is often set by propagation from a VMStatus error and
    does not necessarily mean the Cinder volume itself is bad.
    """

    user = serializers.CharField(source='user.username')
    desktop_type = serializers.CharField(source='operating_system')
    expires = serializers.SerializerMethodField()
    backup_expires = serializers.SerializerMethodField()

    class Meta:
        model = Volume
        fields = ('id', 'user', 'desktop_type', 'zone', 'image', 'flavor',
                  'hostname_id', 'created', 'ready', 'checked_in',
                  'shelved_at', 'archived_at', 'rebooted_at', 'backup_id',
                  'expires', 'backup_expires', 'marked_for_deletion',
                  'deleted', 'error_flag', 'error_message')

    def get_expires(self, volume):
        return volume.get_expires()

    def get_backup_expires(self, volume):
        expiration = volume.backup_expiration
        return expiration.expires if expiration else None


class InstanceSerializer(serializers.ModelSerializer):
    """An Instance record.  Its id IS the Nova server UUID.

    Instances are disposable (shelving deletes the server and keeps
    the boot volume).  The VM's local login credentials are
    deliberately not exposed.
    """

    user = serializers.CharField(source='user.username')
    boot_volume_id = serializers.SerializerMethodField()
    expires = serializers.SerializerMethodField()

    class Meta:
        model = Instance
        fields = ('id', 'user', 'boot_volume_id', 'ip_address', 'created',
                  'expires', 'marked_for_deletion', 'deleted',
                  'error_flag', 'error_message')

    def get_boot_volume_id(self, instance):
        return str(instance.boot_volume.id) if instance.boot_volume else None

    def get_expires(self, instance):
        return instance.get_expires()


class VMStatusSerializer(serializers.ModelSerializer):
    """A VMStatus record: one workflow state for a desktop.

    Unlike /desktops/ (which reports only the latest record per user
    and desktop type), this is the full status history.
    """

    user = serializers.CharField(source='user.username')
    desktop_type = serializers.CharField(source='operating_system')
    instance_id = serializers.SerializerMethodField()

    class Meta:
        model = VMStatus
        fields = ('id', 'user', 'desktop_type', 'status',
                  'status_progress', 'status_message', 'instance_id',
                  'created', 'wait_time')

    def get_instance_id(self, vm_status):
        return (str(vm_status.instance.id)
                if vm_status.instance else None)


class ResizeSerializer(serializers.ModelSerializer):
    """A Resize (boost) record for an instance.

    A resize with reverted unset on a deleted or downsized desktop is
    the marker for manual cleanup ('revert the unreverted Resize').
    """

    instance_id = serializers.SerializerMethodField()
    expires = serializers.SerializerMethodField()

    class Meta:
        model = Resize
        fields = ('id', 'instance_id', 'requested', 'reverted', 'expires')

    def get_instance_id(self, resize):
        return str(resize.instance.id) if resize.instance else None

    def get_expires(self, resize):
        return resize.get_expires()
