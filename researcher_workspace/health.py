from health_check.backends import BaseHealthCheckBackend
from health_check.exceptions import ServiceWarning

from vm_manager import models as vm_models
from vm_manager.constants import VM_ERROR


class DesktopStatus(BaseHealthCheckBackend):
    # Respond with a 200 status code even if the check errors.
    critical_service = False

    def check_status(self):
        vm_errors = vm_models.VMStatus.objects.filter(status=VM_ERROR)
        if vm_errors:
            num_errors = len(vm_errors)
            raise ServiceWarning(f"{num_errors} desktops in ERROR state")

    def identifier(self):
        return self.__class__.__name__
