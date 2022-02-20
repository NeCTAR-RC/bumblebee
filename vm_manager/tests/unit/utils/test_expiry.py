import uuid
from datetime import datetime, timedelta

from unittest.mock import Mock, patch

from django.test import TestCase
from django.conf import settings
from django.utils.timezone import utc

from researcher_desktop.utils.utils import get_desktop_type, desktops_feature
from researcher_desktop.tests.factories import AvailabilityZoneFactory

from vm_manager.utils.expiry import ExpiryPolicy, \
    BoostExpiryPolicy, InstanceExpiryPolicy
from vm_manager.tests.factories import VolumeFactory, InstanceFactory, \
    ResizeFactory
from researcher_workspace.tests.factories import UserFactory


class DummyResource(object):
    def __init__(self, created, expires):
        self.created = created
        self.expires = expires

    def get_expires(self):
        return self.expires


class ExpiryTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.FEATURE = desktops_feature()
        self.UBUNTU = get_desktop_type('ubuntu')
        self.user = UserFactory.create()

    def build_instance(self, expires=None):
        fake_volume = VolumeFactory.create(
            id=uuid.uuid4(),
            user=self.user,
            image=uuid.uuid4(),
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            zone="a_zone",
            flavor=uuid.uuid4())
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(),
            boot_volume=fake_volume,
            user=self.user,
            expires=expires)
        return fake_instance

    def test_initial_expiry(self):
        now = datetime.now(utc)
        boost_policy = BoostExpiryPolicy()
        instance_policy = InstanceExpiryPolicy()

        self.assertEqual(now + timedelta(days=settings.BOOST_EXPIRY),
                         boost_policy.initial_expiry(now))
        self.assertTrue((now + timedelta(days=settings.BOOST_EXPIRY))
                        <= boost_policy.initial_expiry())

        self.assertEqual(now + timedelta(days=settings.INSTANCE_EXPIRY),
                         instance_policy.initial_expiry(now))
        self.assertTrue((now + timedelta(days=settings.INSTANCE_EXPIRY))
                        <= instance_policy.initial_expiry())

    @patch('vm_manager.utils.expiry.datetime')
    def test_permitted_extension(self, mock_datetime):
        now = datetime.now(utc)
        mock_datetime.now.return_value = now

        limited_policy = ExpiryPolicy(1, 1, 5)
        unlimited_policy = ExpiryPolicy(1, 1, -1)

        # A resource with no expiry set cannot be extended
        resource = DummyResource(now, None)
        self.assertEqual(
            timedelta(seconds=0),
            limited_policy.permitted_extension(resource))

        # A resource that is expired but not beyond the resource lifetime
        # can be extended
        resource.expires = now
        self.assertEqual(
            timedelta(days=1),
            limited_policy.permitted_extension(resource))

        # Cannot renew beyond the resource lifetime
        resource.created = now - timedelta(days=5)
        self.assertEqual(
            timedelta(seconds=0),
            limited_policy.permitted_extension(resource))

        # But it is OK if the resource type has no lifetime
        resource.created = now - timedelta(days=5)
        self.assertEqual(
            timedelta(days=1),
            unlimited_policy.permitted_extension(resource))

        # A resource whose current expiration is set to beyond
        # what the extension would be cannot be extended (now)
        resource.created = now
        resource.expires = now + timedelta(days=1)
        self.assertEqual(
            timedelta(seconds=0),
            limited_policy.permitted_extension(resource))

        # But just being in the future is OK
        resource.creates = now
        resource.expires = now + timedelta(seconds=1000)
        self.assertEqual(
            timedelta(days=1),
            limited_policy.permitted_extension(resource))

    @patch('vm_manager.utils.expiry.datetime')
    def test_new_expiry(self, mock_datetime):
        now = datetime.now(utc)
        mock_datetime.now.return_value = now

        limited_policy = ExpiryPolicy(1, 1, 5)
        resource = DummyResource(now, now)

        self.assertEqual(
            now + timedelta(days=1),
            limited_policy.new_expiry(resource))

        resource.expires = None
        self.assertIsNone(
            limited_policy.new_expiry(resource))
