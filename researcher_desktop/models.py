import logging

from functools import cached_property

from django.db import models
from django.conf import settings
from django.urls import reverse

from researcher_workspace import models as workspace_models
from vm_manager.utils.utils import get_nectar

from researcher_desktop.constants import NOTIFY_VM_PATH_PLACEHOLDER
from researcher_desktop.utils.user_data_ubuntu import user_data_ubuntu
from researcher_desktop.utils.user_data_windows import user_data_windows


logger = logging.getLogger(__name__)


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

    @property
    def default_flavor_id(self):
        return self._flavor_id_map[self.default_flavor_name]

    @property
    def big_flavor_id(self):
        return self._flavor_id_map[self.big_flavor_name]

    @cached_property
    def _flavor_id_map(self):
        res = {}
        for f in get_nectar().nova.flavors.list():
            res[f.name] = f.id
        return res

    @cached_property
    def source_volume_id(self):
        return get_nectar().cinder.volumes.list(
            search_opts={'name': self.image_name})[0].id

    def get_user_data(self):
        # FIX ME - this shouldn't be hardwired
        return user_data_ubuntu.replace(
            NOTIFY_VM_PATH_PLACEHOLDER,
            reverse('researcher_desktop:notify_vm'))

    @property
    def security_groups(self):
        # FIX ME - this possibly shouldn't be hardwired
        return settings.OS_SECGROUPS
