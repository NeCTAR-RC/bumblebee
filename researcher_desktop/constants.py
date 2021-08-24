from researcher_workspace.settings import LINUX_IMAGE_NAME, WINDOWS_IMAGE_NAME
from vm_manager.constants import LINUX, WINDOWS

# Dictionary of image names for vm_manager
IMAGE_NAME = {
    LINUX: LINUX_IMAGE_NAME,
    WINDOWS: WINDOWS_IMAGE_NAME
}

BIG_FLAVOR = "m3.xxlarge"
DEFAULT_FLAVOR = "m3.medium"

SUPERSIZE_FLAVOR = "big_flavor"
DEFAULTSIZE_FLAVOR = "default_flavor"

NOTIFY_VM_PATH_PLACEHOLDER = "NOTIFY_VM_PATH_PLACEHOLDER"

APP_NAME = 'researcher_desktop'
