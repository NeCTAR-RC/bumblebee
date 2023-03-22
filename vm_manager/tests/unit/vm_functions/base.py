from datetime import datetime
import uuid

from django.test import TestCase
from django.utils.timezone import utc

from researcher_workspace.tests.factories import UserFactory
from researcher_desktop.utils.utils import get_desktop_type, desktops_feature
from researcher_desktop.tests.factories import AvailabilityZoneFactory

from vm_manager.tests.common import UUID_3, UUID_4
from vm_manager.tests.factories import InstanceFactory, VMStatusFactory, \
    VolumeFactory

from vm_manager.constants import VM_OKAY


class VMFunctionTestBase(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.FEATURE = desktops_feature()
        self.UBUNTU = get_desktop_type('ubuntu')
        self.UBUNTU_source_volume_id = uuid.uuid4()
        self.CENTOS = get_desktop_type('centos')
        self.user = UserFactory.create()
        self.zone = AvailabilityZoneFactory.create(
            name="a_zone", zone_weight=1,
            network_id=uuid.uuid4())

    def build_fake_volume(self, id=None, stage=None):
        if id is None:
            id = UUID_3
        fake_volume = VolumeFactory.create(
            id=id,
            user=self.user,
            image=self.UBUNTU_source_volume_id,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            zone=self.zone.name,
            flavor=self.UBUNTU.default_flavor.id)
        if stage is not None:
            fake_volume.set_expires(datetime.now(utc), stage=stage)
        return fake_volume

    def build_fake_volume_with_backup(self, stage=None):
        backup_id = uuid.uuid4()
        fake_volume = self.build_fake_volume()
        fake_volume.archived_at = datetime.now(utc)
        fake_volume.backup_id = backup_id
        fake_volume.save()
        if stage is not None:
            fake_volume.set_backup_expires(datetime.now(utc), stage=stage)
        return fake_volume, backup_id

    def build_fake_vol_instance(self, volume_id=None, instance_id=None,
                                ip_address=None, expires=None):
        if instance_id is None:
            instance_id = UUID_4
        fake_volume = self.build_fake_volume(id=volume_id)
        fake_instance = InstanceFactory.create(
            id=instance_id,
            boot_volume=fake_volume,
            user=self.user,
            ip_address=ip_address)
        if expires:
            fake_instance.set_expires(expires)
        return fake_volume, fake_instance

    def build_fake_vol_inst_status(self, volume_id=None, instance_id=None,
                                   ip_address=None, status=VM_OKAY,
                                   status_progress=0, expires=None):
        fake_volume, fake_instance = self.build_fake_vol_instance(
            volume_id=volume_id,
            instance_id=instance_id,
            ip_address=ip_address,
            expires=expires)
        fake_vmstatus = VMStatusFactory.create(
            user=self.user,
            instance=fake_instance,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            status=status,
            status_progress=status_progress)
        return fake_volume, fake_instance, fake_vmstatus
