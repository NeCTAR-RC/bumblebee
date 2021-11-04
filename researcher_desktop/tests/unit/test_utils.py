from django.test import TestCase

from django.http import Http404

from researcher_desktop.tests.factories import DomainFactory, \
    AvailabilityZoneFactory, DesktopTypeFactory
from researcher_desktop.models import AvailabilityZone
from researcher_desktop.utils.utils import desktop_types, get_desktop_type, \
    desktops_feature, get_best_zone, do_get_best_zone, get_applicable_zones


class UtilsTests(TestCase):

    def test_desktop_types(self):
        # Assuming that the types are as populated by the 'bootstrap'
        # migration.  This may need to change ...
        types = list(desktop_types())
        self.assertEqual(3, len(types))
        self.assertEqual('ubuntu', types[0].id)
        self.assertEqual('centos', types[1].id)
        self.assertEqual('tern', types[2].id)
        self.assertEqual(1, types[2].restrict_to_zones.count())

    def test_get_desktop_type(self):
        desktop_type = get_desktop_type('ubuntu')
        self.assertEqual('ubuntu', desktop_type.id)
        self.assertRaises(Http404, get_desktop_type, 'unknown')

    def test_desktops_feature(self):
        self.assertIsNotNone(desktops_feature())

    def _populate_zones(self):
        zone_1 = AvailabilityZoneFactory.create(name="az1", zone_weight=1)
        zone_2 = AvailabilityZoneFactory.create(name="az2", zone_weight=3)
        zone_3 = AvailabilityZoneFactory.create(name="azd", zone_weight=2,
                                                enabled=False)
        domain_1 = DomainFactory.create(name="dom1.com", zone=zone_1)
        domain_2 = DomainFactory.create(name="dom2.com", zone=zone_1)
        domain_3 = DomainFactory.create(name="dom3.com", zone=zone_2)
        domain_4 = DomainFactory.create(name="dom4.com", zone=zone_3)

    def test_get_best_zone(self):
        self._populate_zones()

        # Tests for a DesktopType without any zone restriction
        dt = DesktopTypeFactory.create(feature=desktops_feature())
        self.assertEqual("az1",
                         do_get_best_zone("foo@dom1.com", dt, None).name)
        self.assertEqual("az1",
                         do_get_best_zone("foo@dom2.com", dt, None).name)
        self.assertEqual("az2",
                         do_get_best_zone("foo@dom3.com", dt, None).name)
        self.assertEqual("az1",   # Fallback, 'cos "az3" is disabled
                         do_get_best_zone("foo@dom4.com", dt, None).name)

        self.assertEqual("az1",
                         do_get_best_zone("foo@dom1.com", dt, "az1").name)
        self.assertEqual("az2",
                         do_get_best_zone("foo@dom1.com", dt, "az2").name)

        # The requested zone is disabled
        self.assertIsNone(do_get_best_zone("foo@dom1.com", dt, "az3"))
        with self.assertRaises(Http404):
            get_best_zone("foo@dom1.com", dt, "az3")

        # Repeat with a zone restricted DesktopType
        dt.restrict_to_zones.add(AvailabilityZone.objects.get(name="az1"))
        dt.save()
        self.assertEqual("az1",
                         do_get_best_zone("foo@dom1.com", dt, None).name)
        self.assertEqual("az1",
                         do_get_best_zone("foo@dom3.com", dt, None).name)

        self.assertEqual("az1",
                         do_get_best_zone("foo@dom1.com", dt, "az1").name)
        with self.assertRaises(Http404):
            get_best_zone("foo@dom1.com", dt, "az2")

    def test_get_test_applicable_zones(self):
        self._populate_zones()

        # Tests for a DesktopType without any zone restriction
        dt = DesktopTypeFactory.create(feature=desktops_feature())
        all_zones = set(AvailabilityZone.objects.filter(enabled=True))

        zones = get_applicable_zones(dt)
        self.assertEqual(all_zones, set(zones))

        # Repeat with a zone restricted DesktopType
        az1 = AvailabilityZone.objects.get(name="az1")
        dt.restrict_to_zones.add(az1)
        dt.save()
        zones = get_applicable_zones(dt)
        self.assertEqual({az1}, set(zones))
