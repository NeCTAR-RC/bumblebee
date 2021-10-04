import logging
import nanoid
import socket
import string

from datetime import datetime, timezone
from django.db import models
from django.db.utils import IntegrityError
from django.http import Http404
from django.template.defaultfilters import safe

from researcher_workspace.models import Feature, User
from vm_manager.constants import ERROR, ACTIVE, SHUTDOWN, VERIFY_RESIZE, \
    RESIZE, VM_WAITING, VM_ERROR

from vm_manager.utils.utils import get_nectar
from vm_manager.utils.utils import generate_password

from guacamole.models import GuacamoleConnection, \
    GuacamoleConnectionParameter, GuacamoleConnectionPermission, \
    GuacamoleEntity
from guacamole import utils as guac_utils

logger = logging.getLogger(__name__)


class CloudResource(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, )
    created = models.DateTimeField(auto_now_add=True)
    marked_for_deletion = models.DateTimeField(null=True, blank=True)
    deleted = models.DateTimeField(null=True, blank=True)
    error_flag = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=200, null=True, blank=True)

    def error(self, msg):
        self.error_flag = datetime.now(timezone.utc)
        self.error_message = msg
        self.save()

    def set_marked_for_deletion(self):
        self.marked_for_deletion = datetime.now(timezone.utc)
        self.save()


class VolumeManager(models.Manager):
    def get_volume(self, user, desktop_type):
        try:
            volume = self.get(user=user, operating_system=desktop_type.id,
                              requesting_feature=desktop_type.feature,
                              marked_for_deletion=None, error_flag=None)
            return volume
        except Volume.DoesNotExist:
            return None
        except Volume.MultipleObjectsReturned as e:
            logger.error(e)
            error = Volume.MultipleObjectsReturned(
                f"Multiple current volumes found in the database with "
                f"user={user} and os={operating_system}")
            logger.error(error)
            raise error


class Volume(CloudResource):
    image = models.CharField(max_length=100)
    operating_system = models.CharField(max_length=20)
    flavor = models.UUIDField()
    requesting_feature = models.ForeignKey(Feature,
                                           on_delete=models.PROTECT)
    checked_in = models.BooleanField(default=False)
    ready = models.BooleanField(default=False)
    hostname_id = models.CharField(max_length=6, unique=True, null=True)
    shelved = models.BooleanField(default=False)
    rebooted = models.DateTimeField(null=True, blank=True)

    objects = VolumeManager()

    def __str__(self):
        return (f"({self.id}) Volume of {self.operating_system} "
                f"for {self.user}")

    def save(self, *args, **kwargs):
        if not self.hostname_id:
            hostname_id = _create_hostname_id()
            if hostname_id == ERROR:
                logger.error(
                    f"Could not assign random value to volume "
                    f"{self.id} for user {self.user}")
                n = get_nectar()
                n.cinder.volumes.delete(self.id)
                raise ValueError("Could not assign random value to volume")
            self.hostname_id = hostname_id
        super().save(*args, **kwargs)


def _create_hostname_id():
    n = 0
    while n < 100:
        id_value = nanoid.generate(string.ascii_lowercase + string.digits, 6)
        try:
            Volume.objects.get(hostname_id=id_value)
        except Volume.DoesNotExist:
            return id_value
        n += 1
    return ERROR


class InstanceManager(models.Manager):
    def get_instance(self, user, desktop_type):
        try:
            instance = self.get(
                user=user,
                boot_volume__operating_system=desktop_type.id,
                boot_volume__requesting_feature=desktop_type.feature,
                marked_for_deletion=None, error_flag=None)
            return instance
        except Instance.DoesNotExist:
            return None
        except Instance.MultipleObjectsReturned as e:
            logger.error(e)
            error = Instance.MultipleObjectsReturned(
                f"Multiple current instances found in the database with "
                f"user={user} and os={operating_system}")
            logger.error(error)
            raise error

    def get_instance_by_ip_address(self, ip_address, requesting_feature):
        try:
            try:
                instance = self.get(
                    ip_address=ip_address,
                    marked_for_deletion=None, error_flag=None,
                    boot_volume__requesting_feature=requesting_feature)
                return instance
            except Instance.DoesNotExist:
                instances = self.filter(
                    ip_address=None,
                    marked_for_deletion=None, error_flag=None,
                    boot_volume__requesting_feature=requesting_feature)
                for instance in instances:
                    instance.get_ip_addr()
                instance = self.get(
                    ip_address=ip_address,
                    marked_for_deletion=None, error_flag=None,
                    boot_volume__requesting_feature=requesting_feature)
                return instance
        except Instance.DoesNotExist:
            return None
        except Instance.MultipleObjectsReturned as e:
            logger.error(e)
            error = Instance.MultipleObjectsReturned(
                f"Multiple current instances found in the database "
                f"with ip_address={ip_address}")
            logger.error(error)
            raise error

    # vm_id is untrusted because it comes from the user, so should
    # be handled with care
    def get_instance_by_untrusted_vm_id(self, vm_id, user,
                                        requesting_feature):
        # Get vm, and catch any errors
        try:
            instance = self.get(id=vm_id)
        except ValueError:
            logger.error(
                f"Value error trying to get a VM with "
                f"vm_id: {vm_id}, called by {user}")
            raise Http404
        except Instance.DoesNotExist:
            logger.error(
                f"Trying to get a vm that doesn't exist "
                f"with vm_id: {vm_id}, called by {user}")
            raise Http404
        if instance.user != user:
            logger.error(
                f"Trying to get a vm that doesn't belong "
                f"to {user} with vm_id: {vm_id}, "
                f"this vm belongs to {instance.user}")
            raise Http404
        if instance.boot_volume.requesting_feature != requesting_feature:
            logger.error(
                f"Trying to get a vm that doesn't belong "
                f"to {requesting_feature} with vm_id: {vm_id}. This vm "
                f"belongs to {instance.boot_volume.requesting_feature}")
            raise Http404
        if instance.marked_for_deletion:
            if instance.deleted:
                logger.error(
                    f"Trying to get a vm that has been deleted "
                    f"with vm_id: {vm_id}, called by {user}")
            else:
                logger.error(
                    f"Trying to get a vm that is marked for "
                    f"deletion - vm_id: {vm_id}, called by {user}")
            raise Http404
        return instance


class Instance(CloudResource):
    boot_volume = models.ForeignKey(Volume, on_delete=models.PROTECT, )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    guac_connection = models.ForeignKey(GuacamoleConnection,
        on_delete=models.SET_NULL, null=True, blank=True)
    username = models.CharField(max_length=20)
    password = models.CharField(max_length=32)

    objects = InstanceManager()

    def get_ip_addr(self):
        if self.ip_address:
            return self.ip_address
        else:
            n = get_nectar()
            nova_server = n.nova.servers.get(self.id)
            for key in nova_server.addresses:
                self.ip_address = nova_server.addresses[key][0]['addr']
                self.save()
            return self.ip_address

    def create_guac_connection(self):
        params = [
            ('hostname', self.get_ip_addr()),
            ('username', self.username),
            ('password', self.password),
            ('security', 'tls'),
            ('ignore-cert', 'true'),
            ('resize-method', 'display-update'),
            ('enable-drive', 'true'),
            ('drive-path', '/var/lib/guacd/shared-drive'),
            ('create-drive-path', 'true'),
        ]

        connection_params = []
        for k, v in params:
            GuacamoleConnectionParameter.objects.get_or_create(
                connection=self.guac_connection,
                parameter_name=k,
                parameter_value=v)

        entity, _ = GuacamoleEntity.objects.get_or_create(
            name=self.user.username)

        gmodel = GuacamoleConnectionPermission.objects.get_or_create(
            entity=entity,
            connection=self.guac_connection,
            permission='READ')

    def get_url(self):
        # TODO: Set some sort of error if no guac connection set
        self.create_guac_connection()
        return guac_utils.get_direct_url(self.guac_connection)

    def get_status(self):
        n = get_nectar()
        instance_result = n.nova.servers.get(self.id)
        return instance_result.status

    def check_active_status(self):
        return self.get_status() == ACTIVE

    def check_active_or_resize_statuses(self):
        return self.get_status() in (ACTIVE, VERIFY_RESIZE, RESIZE)

    def check_resizing_status(self):
        return self.get_status() == RESIZE

    def check_shutdown_status(self):
        return self.get_status() == SHUTDOWN

    def check_verify_resize_status(self):
        return self.get_status() == VERIFY_RESIZE

    def boot_volume_fields(self):
        return safe('\n'.join(
            [f'<div><label>{field.name}:</label>'
             f'<p>{getattr(self.boot_volume, field.name)}</p></div><hr>'
             for field in self.boot_volume._meta.fields]))

    def __str__(self):
        return (
            f"({self.id}) Instance of {self.boot_volume.operating_system}"
            f" for {self.user} at {self.ip_address}")


class ResizeManager(models.Manager):
    def get_latest_resize(self, instance):
        try:
            resize = self.filter(instance=instance).latest("requested")
            return resize
        except Resize.DoesNotExist:
            return None


class Resize(models.Model):
    instance = models.ForeignKey(Instance, on_delete=models.PROTECT, )
    requested = models.DateTimeField(auto_now_add=True)
    expires = models.DateField(null=True, blank=True)
    reverted = models.DateTimeField(null=True, blank=True)

    objects = ResizeManager()

    def expired(self):
        return self.reverted or self.instance.deleted

    def __str__(self):
        if self.expired():
            current = "Expired"
        else:
            current = "Current"
        return (
            f"Resize ({current}) of Instance ({self.instance.id}) "
            f"requested on {self.requested.date()}")


class VMStatusManager(models.Manager):
    def get_latest_vm_status(self, user, desktop_type):
        try:
            vm_status = self.filter(
                user=user,
                operating_system=desktop_type.id,
                requesting_feature=desktop_type.feature).latest("created")
            return vm_status
        except VMStatus.DoesNotExist:
            return None

    def get_vm_status_by_instance(self, instance, requesting_feature):
        try:
            vm_status = self.get(instance=instance,
                                 requesting_feature=requesting_feature)
            return vm_status
        except VMStatus.MultipleObjectsReturned as e:
            logger.error(e)
            error = VMStatus.MultipleObjectsReturned(
                f"Multiple vm_statuses found in the database "
                f"with instance={instance}")
            logger.error(error)
            raise error

    def get_vm_status_by_volume(self, volume, requesting_feature):
        if volume.requesting_feature != requesting_feature:
            logger.error(
                f"Trying to get a vm that doesn't belong to "
                f"{requesting_feature} with vm_id: {volume.id}"
                f"this vm belongs to {volume.requesting_feature}")
            raise Http404
        try:
            instance = Instance.objects.filter(boot_volume=volume) \
                                       .latest("created")
        except Exception as e:
            logger.error(
                f"Trying to get_vm_status_by_volume {volume}, "
                f"could not find an instance with that volume,"
                f"raised error {e}")
            raise e
        try:
            vm_status = self.get(instance=instance,
                                 requesting_feature=requesting_feature)
            return vm_status
        except VMStatus.MultipleObjectsReturned as e:
            logger.error(e)
            error = VMStatus.MultipleObjectsReturned(
                f"Multiple vm_statuses found in the database "
                f"with instance={instance}")
            logger.error(error)
            raise error

    # vm_id is untrusted because it comes from the user, so should
    # be handled with care
    def get_vm_status_by_untrusted_vm_id(self, vm_id, user,
                                         requesting_feature):
        # Get vm, and catch any errors
        instance = Instance.objects.get_instance_by_untrusted_vm_id(
            vm_id, user, requesting_feature)
        # Get vm_status
        vm_status = self.get_vm_status_by_instance(
            instance, requesting_feature)
        return vm_status


class VMStatus(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    created = models.DateTimeField(auto_now_add=True)
    requesting_feature = models.ForeignKey(Feature, on_delete=models.PROTECT)
    operating_system = models.CharField(max_length=20)
    instance = models.ForeignKey(
        Instance, on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=20)
    wait_time = models.DateTimeField(null=True, blank=True)

    def error(self, message):
        self.status = VM_ERROR
        self.save()
        self.instance.error(message)
        self.instance.boot_volume.error(message)

    class Meta:
        verbose_name = 'VM Status'
        verbose_name_plural = 'VM Statuses'
    objects = VMStatusManager()

    def __str__(self):
        return (
            f"Status of [{self.requesting_feature}]"
            f"[{self.operating_system}][{self.user}] is {self.status}")
