import uuid

from vm_manager.constants import VM_OKAY
from vm_manager.tests.factories import InstanceFactory, VMStatusFactory, \
    VolumeFactory


def make_desktop(user, desktop_id, feature, status=VM_OKAY,
                 deleted=None, zone='QRIScloud'):
    """Create a Volume, Instance and VMStatus for a user's desktop."""
    volume = VolumeFactory.create(
        id=uuid.uuid4(), user=user, operating_system=desktop_id,
        requesting_feature=feature, zone=zone)
    instance = InstanceFactory.create(
        id=uuid.uuid4(), user=user, boot_volume=volume,
        deleted=deleted)
    return VMStatusFactory.create(
        user=user, operating_system=desktop_id,
        requesting_feature=feature, instance=instance,
        status=status)
