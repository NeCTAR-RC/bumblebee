import logging

from functools import cached_property

from django.conf import settings
from django.db import models

from researcher_workspace import models as workspace_models
from vm_manager.utils.utils import get_nectar, FlavorDetails


logger = logging.getLogger(__name__)


class AvailabilityZone(models.Model):
    name = models.CharField(primary_key=True, max_length=32)
    zone_weight = models.IntegerField()
    network_id = workspace_models.Char32UUIDField(null=True)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name}"


class Domain(models.Model):
    name = models.CharField(primary_key=True, max_length=128)
    zone = models.ForeignKey(AvailabilityZone,
                             on_delete=models.CASCADE,
                             related_name='domains')

    def __str__(self):
        return f"{self.name}"


class DesktopTypeManager(models.Manager):
    def get_desktop_type(self, id):
        try:
            return self.get(id=id)
        except DesktopType.DoesNotExist:
            return None


class DesktopType(models.Model):
    id = models.CharField(primary_key=True, max_length=32)
    name = models.CharField(max_length=128)
    description = models.TextField()
    logo = models.URLField(blank=True, null=True)
    image_name = models.CharField(max_length=256)
    default_flavor_name = models.CharField(max_length=32)
    big_flavor_name = models.CharField(max_length=32)
    volume_size = models.IntegerField(default=30, help_text="Size in GB")
    feature = models.ForeignKey(workspace_models.Feature,
                                on_delete=models.PROTECT)
    enabled = models.BooleanField(default=True)
    restrict_to_zones = models.ManyToManyField(AvailabilityZone, blank=True)
    details = models.JSONField(blank=True, null=True)
    family = models.CharField(default="linux", max_length=32,
                              help_text="Selects a cloud-config template;"
                              "e.g. 'linux' or 'windows'")
    # This is added to the LAUNCH_WAIT, REBOOT_WAIT and RESIZE_WAIT
    # settings to give actual wait times when launching (etc) desktop.
    launch_wait_extra = models.IntegerField(default=0,
                                            help_text="Extra launch wait "
                                            "time in seconds")

    objects = DesktopTypeManager()

    def __str__(self):
        return f"{self.id}"

    @property
    def default_flavor(self):
        return self._flavor_map[self.default_flavor_name]

    @property
    def big_flavor(self):
        return self._flavor_map[self.big_flavor_name]

    @property
    def is_resizable(self):
        return (self.big_flavor_name
                and self.big_flavor_name != self.default_flavor_name)

    @cached_property
    def _flavor_map(self):
        res = {}
        for f in get_nectar().nova.flavors.list():
            res[f.name] = FlavorDetails(f)
        return res

    @property
    def security_groups(self):
        # FIX ME - this possibly shouldn't be hardwired
        return settings.OS_SECGROUPS
