from researcher_workspace.settings import LINUX_IMAGE_NAME, WINDOWS_IMAGE_NAME
from vm_manager.constants import LINUX, WINDOWS

# Dictionary of image names for vm_manager
IMAGE_NAME = {
    LINUX: LINUX_IMAGE_NAME,
    WINDOWS: WINDOWS_IMAGE_NAME
}

HICORES = "High Cores"
FASTCORES = "Fast Cores"

BASIC_FLAVORS = {
    HICORES: "m3.large",
    FASTCORES: "m3.large",
}

OS_CHOICES = [(key, key.capitalize()) for key in IMAGE_NAME.keys()]

NOTIFY_VM_PATH_PLACEHOLDER = "NOTIFY_VM_PATH_PLACEHOLDER"

APP_NAME = 'specialty_resources'
