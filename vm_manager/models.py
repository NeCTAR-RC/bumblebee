from datetime import datetime
import logging
import nanoid
import string

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.http import Http404
from django.template.defaultfilters import safe
from django.utils.timezone import utc

from novaclient import exceptions as nova_exceptions

from researcher_workspace.models import Feature, User
from researcher_desktop.models import DesktopType
from vm_manager.constants import ERROR, ACTIVE, SHUTDOWN, VERIFY_RESIZE, \
    RESIZE, MISSING, VM_ERROR, VM_DELETED

from vm_manager.utils.utils import get_nectar

from guacamole.models import GuacamoleConnection, \
    GuacamoleConnectionParameter, GuacamoleConnectionPermission, \
    GuacamoleEntity
from guacamole import utils as guac_utils

logger = logging.getLogger(__name__)


class Expiration(models.Model):
    expires = models.DateTimeField()
    stage = models.IntegerField(default=0)
    stage_date = models.DateTimeField()

    def __str__(self):
        return (f"Expires on {self.expires}, stage {self.stage}, "
                f"stage_date {self.stage_date}")


class ResourceExpiration(Expiration):
    pass


class ResizeExpiration(Expiration):
    pass


class CloudResource(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, )
    created = models.DateTimeField(auto_now_add=True)
    expiration = models.OneToOneField(ResourceExpiration,
                                      on_delete=models.CASCADE,
                                      null=True,
                                      related_name='expiration_for')
    marked_for_deletion = models.DateTimeField(null=True, blank=True)
    deleted = models.DateTimeField(null=True, blank=True)
    error_flag = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    def error(self, msg):
        self.error_flag = datetime.now(utc)
        self.error_message = msg
        self.save()

    def set_marked_for_deletion(self):
        self.marked_for_deletion = datetime.now(utc)
        self.save()

    def set_expires(self, expires):
        if expires is None:
            self.expiration = None
            self.save()
        elif self.expiration:
            self.expiration.expires = expires
            self.expiration.stage = 0
            self.expiration.stage_date = datetime.now(utc)
            self.expiration.save()
        else:
            self.expiration = ResourceExpiration(expires=expires)
            self.expiration.stage = 0
            self.expiration.stage_date = datetime.now(utc)
            self.expiration.save()
            self.save()

    def get_expires(self):
        return self.expiration.expires if self.expiration else None


class VolumeManager(models.Manager):
    def get_volume(self, user, desktop_type):
        try:
            volume = self.get(user=user, operating_system=desktop_type.id,
                              requesting_feature=desktop_type.feature,
                              deleted=None, marked_for_deletion=None,
                              error_flag=None)
            return volume
        except Volume.DoesNotExist:
            return None
        except Volume.MultipleObjectsReturned as e:
            logger.error(e)
            error = Volume.MultipleObjectsReturned(
                f"Multiple current volumes found in the database with "
                f"user={user} and os={desktop_type.id}")
            logger.error(error)
            raise error


class Volume(CloudResource):
    image = models.CharField(max_length=100)
    operating_system = models.CharField(max_length=20)
    flavor = models.UUIDField()
    zone = models.CharField(max_length=32, null=True)
    requesting_feature = models.ForeignKey(Feature,
                                           on_delete=models.PROTECT)
    checked_in = models.BooleanField(default=False)
    ready = models.BooleanField(default=False)
    hostname_id = models.CharField(max_length=6, unique=True, null=True)
    shelved_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    backup_id = models.UUIDField(null=True, blank=True)
    rebooted_at = models.DateTimeField(null=True, blank=True)

    objects = VolumeManager()

    def __str__(self):
        return (f"Volume {self.id} of {self.operating_system} "
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
                deleted=None, marked_for_deletion=None, error_flag=None)
            return instance
        except Instance.DoesNotExist:
            return None
        except Instance.MultipleObjectsReturned as e:
            logger.error(e)
            error = Instance.MultipleObjectsReturned(
                f"Multiple current instances found in the database with "
                f"user={user} and os={desktop_type.name}")
            logger.error(error)
            raise error

    def get_latest_instance_for_volume(self, volume):
        '''Return the latest created Instance for a Volume, irrespective of
        deletion status.
        '''
        try:
            return self.filter(boot_volume=volume).order_by('-created').first()
        except Instance.DoesNotExist:
            return None

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
        instance = self.get_instance_by_untrusted_vm_id_2(
            vm_id, requesting_feature, user=user)
        if instance.user != user:
            logger.error(
                f"Trying to get a vm that doesn't belong "
                f"to {user} with vm_id: {vm_id}, "
                f"this vm belongs to {instance.user}")
            raise Http404
        return instance

    # vm_id is untrusted because it comes from the user, so should
    # be handled with care.  In this version, the request is anonymous.
    def get_instance_by_untrusted_vm_id_2(self, vm_id, requesting_feature,
                                          user="internal"):
        # Get vm, and catch any errors
        try:
            instance = self.get(id=vm_id)
        except ValueError:
            logger.error(
                f"Value error trying to get a VM with "
                f"vm_id: {vm_id}, called by {user}")
            raise Http404
        except ValidationError as e:
            logger.error(
                f"Validation error ({e}) trying to get a VM with "
                f"vm_id: {vm_id}, called by {user}")
            raise Http404
        except Instance.DoesNotExist:
            logger.error(
                f"Trying to get a vm that doesn't exist "
                f"with vm_id: {vm_id}, called by {user}")
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

        for k, v in params:
            gcp, created = GuacamoleConnectionParameter.objects.get_or_create(
                connection=self.guac_connection,
                parameter_name=k,
                defaults={'parameter_value': v})
            if not created:
                gcp.parameter_value = v

        entity, _ = GuacamoleEntity.objects.get_or_create(
            name=self.user.username)

        gmodel = GuacamoleConnectionPermission.objects.get_or_create(
            entity=entity,
            connection=self.guac_connection,
            permission='READ')

    def get_url(self):
        # TODO: Set some sort of error if no guac connection set
        self.create_guac_connection()
        # e.g. https://bumblebee-guacamole-melbourne-qh2.bumblebee.cloud.edu.au/#/client/MQBjAG15c3Fs
        url = settings.GUACAMOLE_URL_TEMPLATE.format(
            env=settings.ENVIRONMENT_NAME,
            zone=self.boot_volume.zone.lower(),  # lowercase for FQDN
            path=guac_utils.get_connection_path(self.guac_connection)
        )
        return url

    def get_status(self):
        n = get_nectar()
        try:
            instance_result = n.nova.servers.get(self.id)
            return instance_result.status
        except nova_exceptions.NotFound:
            return MISSING

    def check_active_status(self):
        return self.get_status() == ACTIVE

    def check_active_or_resize_statuses(self):
        return self.get_status() in {ACTIVE, VERIFY_RESIZE, RESIZE}

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
        return (f" Instance {self.id} of {self.boot_volume.operating_system}"
                f" for {self.user}")


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
    expiration = models.OneToOneField(ResizeExpiration,
                                      on_delete=models.CASCADE,
                                      null=True,
                                      related_name='expiration_for')
    reverted = models.DateTimeField(null=True, blank=True)

    objects = ResizeManager()

    def expired(self):
        return self.reverted or self.instance.deleted

    def set_expires(self, expires):
        if expires is None:
            self.expiration = None
            self.save()
        elif self.expiration:
            self.expiration.expires = expires
            self.expiration.stage = 0
            self.expiration.stage_date = datetime.now(utc)
            self.expiration.save()
        else:
            self.expiration = ResizeExpiration(expires=expires)
            self.expiration.stage = 0
            self.expiration.stage_date = datetime.now(utc)
            self.expiration.save()
            self.save()

    def get_expires(self):
        return self.expiration.expires if self.expiration else None

    def __str__(self):
        if self.expired():
            current = "Expired"
        else:
            current = "Current"
        return (
            f"Resize ({current}) of Instance ({self.instance.id}) "
            f"requested on {self.requested}")


class VMStatusManager(models.Manager):
    def get_latest_vm_statuses(self, user, excluded_states=[VM_DELETED]):
        """This is used to check if a User has any live desktop instances.
        We check each desktop type, and look for the latest VMStatus for
        the user.  If it is not in the excluded states, we include it
        in the result list.
        """
        statuses = []
        for desktop_type in DesktopType.objects.all():
            # Note that this includes disabled DesktopTypes.
            vm_status = self.get_latest_vm_status(user, desktop_type)
            if vm_status and vm_status.status not in excluded_states:
                statuses.append(vm_status)
        return statuses

    def get_latest_vm_status(self, user, desktop_type):
        """Get the latest VMStatus for this User and DesktopType in
        any state.  Returns None if there are none.
        """
        try:
            vm_status = self.filter(
                user=user,
                operating_system=desktop_type.id,
                requesting_feature=desktop_type.feature).latest("created")
            return vm_status
        except VMStatus.DoesNotExist:
            return None

    # TODO - The 'requesting_feature' argument is redundant (AFAIK)
    # In fact it is probably redundant on the model class too.
    def get_vm_status_by_instance(self, instance, requesting_feature):
        try:
            vm_status = self.get(instance=instance,
                                 requesting_feature=requesting_feature)
            return vm_status
        except VMStatus.DoesNotExist as e:
            logger.error(e)
            error = VMStatus.DoesNotExist(
                f"No vm_statuses found in the database "
                f"with instance={instance}")
            logger.error(error)
            raise error
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

        return self.get_vm_status_by_instance(instance, requesting_feature)

    # vm_id is untrusted because it comes from the user, so should
    # be handled with care
    def get_vm_status_by_untrusted_vm_id(self, vm_id, user,
                                         requesting_feature):
        # Get vm, and map any errors to Http404 errors
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
    status_message = models.TextField(null=True, blank=True)
    status_progress = models.IntegerField(default=0)
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
        return (f"Status of {self.operating_system} for {self.user} is "
                f"{self.status}")
