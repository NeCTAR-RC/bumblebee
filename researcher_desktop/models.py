import logging

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

    def get_default_flavor(self):
        return _get_flavor(self.default_flavor_name)

    def get_big_flavor(self):
        return _get_flavor(self.big_flavor_name)

    def _get_flavor(self, name):
        return get_nectar().nova.flavors.list(
            search_opts={'name': name})[0].id

    def get_source_volume(self):
        volumes = get_nectar().cinder.volumes.list(
            search_opts={'name': self.image_name})[0].id

    def get_user_data(self):
        # FIX ME
        return user_data_ubuntu.replace(
            NOTIFY_VM_PATH_PLACEHOLDER,
            reverse('researcher_desktop:notify_vm'))

    def get_security_groups(self):
        return settings.OS_SECGROUPS
