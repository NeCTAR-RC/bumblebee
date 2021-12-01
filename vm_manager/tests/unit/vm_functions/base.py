import uuid

from django.test import TestCase

from researcher_workspace.tests.factories import UserFactory
from researcher_desktop.utils.utils import get_desktop_type, desktops_feature
from researcher_desktop.tests.factories import AvailabilityZoneFactory

from vm_manager.tests.common import UUID_1, UUID_2, UUID_3, UUID_4
from vm_manager.tests.fakes import Fake, FakeServer, FakeVolume, FakeNectar
from vm_manager.tests.factories import InstanceFactory, VMStatusFactory, \
    VolumeFactory

from vm_manager.constants import VM_MISSING, VM_OKAY, VM_SHELVED, NO_VM, \
    VOLUME_CREATION_TIMEOUT


class VMFunctionTestBase(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.FEATURE = desktops_feature()
        self.UBUNTU = get_desktop_type('ubuntu')
        self.UBUNTU_source_volume_id = uuid.uuid4()
        self.CENTOS = get_desktop_type('centos')
        self.user = UserFactory.create()
        self.zone = AvailabilityZoneFactory.create(name="a_zone",
                                                   zone_weight=1)

    def build_fake_volume(self, id=None):
        if id is None:
            id = UUID_3
        return VolumeFactory.create(
            id=id,
            user=self.user,
            image=self.UBUNTU_source_volume_id,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            zone=self.zone.name,
            flavor=self.UBUNTU.default_flavor.id)

    def build_fake_vol_instance(self, volume_id=None, instance_id=None,
                                ip_address=None):
        if instance_id is None:
            instance_id = UUID_4
        fake_volume = self.build_fake_volume(id=volume_id)
        fake_instance = InstanceFactory.create(
            id=instance_id,
            boot_volume=fake_volume,
            user=self.user,
            ip_address=ip_address)
        return fake_volume, fake_instance

    def build_fake_vol_inst_status(self, volume_id=None, instance_id=None,
                                   ip_address=None, status=VM_OKAY):
        fake_volume, fake_instance = self.build_fake_vol_instance(
            volume_id=volume_id,
            instance_id=instance_id,
            ip_address=ip_address)
        fake_vmstatus = VMStatusFactory.create(
            user=self.user,
            instance=fake_instance,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            status=status)
        return fake_volume, fake_instance, fake_vmstatus
