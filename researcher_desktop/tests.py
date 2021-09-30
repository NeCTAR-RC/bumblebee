from django.test import TestCase

from django.http import Http404

from researcher_desktop.utils.utils import desktop_types, get_desktop_type, \
    desktops_feature


class UtilsTests(TestCase):

    def test_desktop_types(self):
        # Assuming that the types are as populated by the 'bootstrap'
        # migration.  This may need to change ...
        types = list(desktop_types())
        self.assertEqual(2, len(types))
        self.assertEqual('ubuntu', types[0].id)
        self.assertEqual('centos', types[1].id)

    def test_get_desktop_type(self):
        desktop_type = get_desktop_type('ubuntu')
        self.assertEqual('ubuntu', desktop_type.id)
        self.assertRaises(Http404, get_desktop_type, 'unknown')

    def test_desktops_feature(self):
        self.assertIsNotNone(desktops_feature())
