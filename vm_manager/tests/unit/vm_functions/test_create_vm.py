from django.test import TestCase

from researcher_workspace.tests.factories import UserFactory
from researcher_desktop.utils.utils import get_desktop_type, desktops_feature

from vm_manager.tests.factories import InstanceFactory, VMStatusFactory, \
    VolumeFactory

class CreateVMTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.FEATURE = desktops_feature()
        self.UBUNTU = get_desktop_type('ubuntu')
        self.CENTOS = get_desktop_type('centos')
        self.user = UserFactory.create()

    def test_launch_has_instance(self):
        volume = VolumeFactory.create(
            user=self.user,
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature)
        instance = InstanceFactory.create(
            user=self.user,
            boot_volume=volume
        )

        self.assertIsNotNone(instance)
