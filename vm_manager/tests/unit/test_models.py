import pdb

import uuid
import copy
from datetime import datetime, timedelta, timezone

from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase

from researcher_workspace.tests.factories import FeatureFactory, UserFactory
from researcher_desktop.tests.factories import DesktopTypeFactory
from vm_manager.tests.factories import VolumeFactory
from vm_manager.tests.fakes import FakeNectar
from vm_manager.constants import ERROR
from vm_manager.utils.utils import get_nectar

from vm_manager.models import Volume, _create_hostname_id


class VolumeModelTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()
        self.feature = FeatureFactory.create(app_name='feature')
        self.desktop_type = DesktopTypeFactory.create(name='desktop',
                                                      feature=self.feature)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.models._create_hostname_id')
    def test_volume_save(self, mock_gen):
        mock_gen.return_value = "fnord"
        id = uuid.uuid4()
        volume = VolumeFactory.create(id=id, user=self.user,
                                      requesting_feature=self.feature)
        self.assertEquals("fnord", volume.hostname_id)
        mock_gen.assert_called_once()

        mock_gen.return_value = ERROR
        id = uuid.uuid4()
        with self.assertRaises(ValueError) as cm:
            volume = VolumeFactory.create(id=id, user=self.user,
                                          requesting_feature=self.feature)
        self.assertEqual("Could not assign random value to volume",
                         str(cm.exception))
        fake = get_nectar()
        fake.cinder.volumes.delete.assert_called_once_with(id)

    @patch('vm_manager.models.nanoid')
    def test_create_hostname_id(self, mock_nanoid):
        mock_nanoid.generate.return_value = "xxxxxx"
        volume = VolumeFactory.create(id=uuid.uuid4(), user=self.user,
                                      requesting_feature=self.feature)
        mock_nanoid.generate.assert_called_once()

        self.assertEqual(ERROR, _create_hostname_id())

        self.assertEqual(101, mock_nanoid.generate.call_count)

    def test_get_volume(self):
        self.assertIsNone(Volume.objects.get_volume(self.user,
                                                    self.desktop_type))
        volume = VolumeFactory.create(id=uuid.uuid4(), user=self.user,
                                      requesting_feature=self.feature)
        self.assertEqual(volume,
                         Volume.objects.get_volume(self.user,
                                                   self.desktop_type))
        volume = VolumeFactory.create(id=uuid.uuid4(), user=self.user,
                                      requesting_feature=self.feature)
        with self.assertRaises(Volume.MultipleObjectsReturned) as cm:
            Volume.objects.get_volume(self.user, self.desktop_type)
        self.assertEquals(
            f"Multiple current volumes found in the database with "
            f"user={self.user} and os={self.desktop_type.id}",
            str(cm.exception))
