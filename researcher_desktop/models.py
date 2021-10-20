import logging

from functools import cached_property

from django.db import models
from django.conf import settings
from django.urls import reverse

from researcher_workspace import models as workspace_models
from vm_manager.utils.utils import get_nectar
from vm_manager.utils.utils import FlavorDetails


logger = logging.getLogger(__name__)


class AvailabilityZone(models.Model):
    name = models.CharField(primary_key=True, max_length=32)
    zone_weight = models.IntegerField()
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.__class__.name}({self.name})"


class Domain(models.Model):
    name = models.CharField(primary_key=True, max_length=128)
    zone = models.ForeignKey(AvailabilityZone,
                             on_delete=models.CASCADE,
                             related_name='domains')

    def __str__(self):
        return f"{self.__class__.name}({self.name})"


class DesktopType(models.Model):
    id = models.CharField(primary_key=True, max_length=32)
    name = models.CharField(max_length=128)
    description = models.TextField()
    logo = models.ImageField(blank=True)
    image_name = models.CharField(max_length=256)
    default_flavor_name = models.CharField(max_length=32)
    big_flavor_name = models.CharField(max_length=32)
    feature = models.ForeignKey(workspace_models.Feature,
                                on_delete=models.PROTECT)
    enabled = models.BooleanField(default=True)
    restrict_to_zones = models.ManyToManyField(AvailabilityZone)

    def __str__(self):
        return f"{self.__class__.name}({self.id})"

    @property
    def default_flavor(self):
        return self._flavor_map[self.default_flavor_name]

    @property
    def big_flavor(self):
        return self._flavor_map[self.big_flavor_name]

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
