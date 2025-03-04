from health_check.backends import BaseHealthCheckBackend
from health_check.exceptions import ServiceWarning

from vm_manager.constants import VM_ERROR
from vm_manager import models as vm_models


class DesktopStatus(BaseHealthCheckBackend):
    # Respond with a 200 status code even if the check errors.
    critical_service = False

    def check_status(self):
        vmstatus_errors = vm_models.VMStatus.objects.filter(status=VM_ERROR)
        if vmstatus_errors:
            num_errors = len(vmstatus_errors)
            raise ServiceWarning(f"{num_errors} desktops in ERROR state")

    def identifier(self):
        return self.__class__.__name__


class InstanceStatus(BaseHealthCheckBackend):
    # Respond with a 200 status code even if the check errors.
    critical_service = False

    def check_status(self):
        instance_errors = vm_models.Instance.objects.filter(
            deleted__isnull=True, error_flag__isnull=False)
        if instance_errors:
            num_errors = len(instance_errors)
            raise ServiceWarning(f"{num_errors} instances in ERROR state")

    def identifier(self):
        return self.__class__.__name__


class VolumeStatus(BaseHealthCheckBackend):
    # Respond with a 200 status code even if the check errors.
    critical_service = False

    def check_status(self):
        volume_errors = vm_models.Volume.objects.filter(
            deleted__isnull=True, error_flag__isnull=False)
        if volume_errors:
            num_errors = len(volume_errors)
            raise ServiceWarning(f"{num_errors} volumes in ERROR state")

    def identifier(self):
        return self.__class__.__name__
