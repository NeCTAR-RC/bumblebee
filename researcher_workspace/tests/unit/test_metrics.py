from unittest.mock import patch
import uuid

from django.db import connection
from django.test import TestCase, override_settings

from researcher_desktop.tests.factories import DesktopTypeFactory
from researcher_workspace.metrics import BumblebeeMetricsCollector
from researcher_workspace.tests.factories import FeatureFactory, UserFactory
from vm_manager.tests.factories import VolumeFactory


def _sqlite_substring_index(s, delim, count):
    if s is None:
        return None
    parts = s.split(delim)
    if count >= 0:
        return delim.join(parts[:count])
    return delim.join(parts[count:])


@override_settings(EXCLUDE_FROM_USAGE=['monitor@example.com'])
class BumblebeeMetricsCollectorTests(TestCase):

    def setUp(self):
        # sqlite does not have a built-in substring_index function;
        # the metrics by_domain query relies on it.
        connection.connection.create_function(
            "substring_index", 3, _sqlite_substring_index)
        self.feature = FeatureFactory.create(app_name='feature')
        self.desktop_type = DesktopTypeFactory.create(
            id='desktop', name='desktop', feature=self.feature)

    def _make_volume(self, user, **kwargs):
        params = {
            'id': uuid.uuid4(),
            'user': user,
            'operating_system': 'ubuntu',
            'requesting_feature': self.feature,
            'zone': 'QRIScloud',
        }
        params.update(kwargs)
        with patch('vm_manager.models._create_hostname_id') as mock_gen:
            mock_gen.return_value = uuid.uuid4().hex[:6]
            return VolumeFactory.create(**params)

    def test_collect_no_volumes(self):
        collector = BumblebeeMetricsCollector()
        metrics = list(collector.collect())
        # 4 metrics per dimension * 3 dimensions
        self.assertEqual(12, len(metrics))
        # all totals are zero
        totals = [m for m in metrics if m.name.endswith("_total")]
        self.assertEqual(3, len(totals))
        for m in totals:
            self.assertEqual(0, m.samples[0].value)

    def test_collect_with_volumes(self):
        user = UserFactory.create(email="researcher@uni.edu.au")
        v1 = self._make_volume(user)
        # one shelved
        from datetime import datetime, timezone
        v2 = self._make_volume(user)
        v2.shelved_at = datetime.now(timezone.utc)
        v2.save()

        collector = BumblebeeMetricsCollector()
        metrics = list(collector.collect())

        names = [m.name for m in metrics]
        self.assertIn("bumblebee_desktops_created_total", names)
        self.assertIn("bumblebee_desktops_running_total", names)
        self.assertIn("bumblebee_desktops_shelved_total", names)

        # type / zone / domain breakdowns are emitted
        by_zone = [m for m in metrics
                   if m.name == "bumblebee_desktops_created_by_zone"][0]
        # at least one zone label present
        self.assertTrue(any(s.labels.get("zone") == "QRIScloud"
                            for s in by_zone.samples))

    def test_collect_excludes_superusers_and_excluded(self):
        super_user = UserFactory.create(
            username="super@uni.edu.au", email="super@uni.edu.au",
            is_superuser=True)
        excluded = UserFactory.create(
            username="monitor@example.com", email="monitor@example.com")
        normal = UserFactory.create(
            username="someone@uni.edu.au", email="someone@uni.edu.au")
        self._make_volume(super_user)
        self._make_volume(excluded)
        self._make_volume(normal)

        # The metrics module imports settings directly from
        # researcher_workspace.settings rather than via django.conf.settings,
        # so override_settings doesn't reach it; patch the module attribute.
        with patch(
                'researcher_workspace.metrics.settings.EXCLUDE_FROM_USAGE',
                ['monitor@example.com']):
            collector = BumblebeeMetricsCollector()
            metrics = list(collector.collect())
        totals = {m.name: m.samples[0].value
                  for m in metrics if m.name.endswith("_total")}
        # super_user volume + excluded user volume excluded; only normal counts
        self.assertEqual(1, totals["bumblebee_desktops_created_total"])
