from django.test import TestCase
from researcher_desktop.utils.utils import desktop_type_ids


class UtilsTests(TestCase):

    def test_desktop_type_ids(self):
        # Assuming that the types are as populated by the 'bootstrap'
        # migration.  This may need to change ...
        ids = desktop_type_ids()
        self.assertEqual(2, len(ids))
        self.assertEqual('ubuntu', ids[0])
        self.assertEqual('centos', ids[1])

