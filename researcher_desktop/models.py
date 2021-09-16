import logging

from django.db import models

logger = logging.getLogger(__name__)


class DesktopType(models.Model):
    name = models.CharField(primary_key=True, max_length=32)
    description = models.CharField(max_length=256, blank=True)
    image_name = models.CharField(max_length=256)
    default_flavor_name = models.CharField(max_length=32)
    big_flavor_name = models.CharField(max_length=32)
    enabled = models.BooleanField(default=True)
