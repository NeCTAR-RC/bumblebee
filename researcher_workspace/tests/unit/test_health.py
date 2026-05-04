from datetime import datetime, timezone
from unittest.mock import patch
import uuid

from django.test import TestCase

from health_check.exceptions import ServiceWarning

from researcher_desktop.tests.factories import DesktopTypeFactory
from researcher_workspace.health import (
    DesktopStatus, InstanceStatus, VolumeStatus,
)
from researcher_workspace.tests.factories import FeatureFactory, UserFactory
from vm_manager.constants import VM_ERROR, VM_OKAY
from vm_manager.tests.factories import (
    InstanceFactory, VMStatusFactory, VolumeFactory,
)

utc = timezone.utc


class HealthCheckTests(TestCase):

    def setUp(self):
        self.user = UserFactory.create()
        self.feature = FeatureFactory.create(app_name='feature')
        self.desktop_type = DesktopTypeFactory.create(
            id='desktop', name='desktop', feature=self.feature)

    def _make_volume(self, **kwargs):
        params = dict(
            id=uuid.uuid4(),
            user=self.user,
            operating_system='ubuntu',
            requesting_feature=self.feature,
            zone='QRIScloud',
        )
        params.update(kwargs)
        with patch('vm_manager.models._create_hostname_id') as m:
            m.return_value = uuid.uuid4().hex[:6]
            return VolumeFactory.create(**params)

    def test_desktop_status_no_errors(self):
        check = DesktopStatus()
        # no errors at all
        check.check_status()
        self.assertEqual("DesktopStatus", check.identifier())

    def test_desktop_status_with_errors(self):
        VMStatusFactory.create(
            user=self.user, requesting_feature=self.feature,
            operating_system='ubuntu', status=VM_ERROR)
        check = DesktopStatus()
        with self.assertRaises(ServiceWarning):
            check.check_status()

    def test_instance_status_no_errors(self):
        check = InstanceStatus()
        check.check_status()
        self.assertEqual("InstanceStatus", check.identifier())

    def test_instance_status_with_errors(self):
        volume = self._make_volume()
        InstanceFactory.create(
            id=uuid.uuid4(),
            user=self.user,
            boot_volume=volume,
            error_flag=datetime.now(utc),
        )
        check = InstanceStatus()
        with self.assertRaises(ServiceWarning):
            check.check_status()

    def test_volume_status_no_errors(self):
        check = VolumeStatus()
        check.check_status()
        self.assertEqual("VolumeStatus", check.identifier())

    def test_volume_status_with_errors(self):
        self._make_volume(error_flag=datetime.now(utc))
        check = VolumeStatus()
        with self.assertRaises(ServiceWarning):
            check.check_status()
