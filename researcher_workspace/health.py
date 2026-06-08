import dataclasses

from health_check.base import HealthCheck
from health_check.exceptions import ServiceWarning

from vm_manager.constants import VM_ERROR
from vm_manager import models as vm_models


@dataclasses.dataclass
class DesktopStatus(HealthCheck):
    def run(self):
        vmstatus_errors = vm_models.VMStatus.objects.filter(status=VM_ERROR)
        if vmstatus_errors:
            num_errors = len(vmstatus_errors)
            raise ServiceWarning(f"{num_errors} desktops in ERROR state")


@dataclasses.dataclass
class InstanceStatus(HealthCheck):
    def run(self):
        instance_errors = vm_models.Instance.objects.filter(
            deleted__isnull=True, error_flag__isnull=False)
        if instance_errors:
            num_errors = len(instance_errors)
            raise ServiceWarning(f"{num_errors} instances in ERROR state")


@dataclasses.dataclass
class VolumeStatus(HealthCheck):
    def run(self):
        volume_errors = vm_models.Volume.objects.filter(
            deleted__isnull=True, error_flag__isnull=False)
        if volume_errors:
            num_errors = len(volume_errors)
            raise ServiceWarning(f"{num_errors} volumes in ERROR state")
