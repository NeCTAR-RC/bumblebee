from django.test import TestCase
from researcher_desktop.utils.utils import desktop_type_names
from researcher_desktop.utils.utils import VMInfo


class UtilsTests(TestCase):

    def test_desktop_type_names(self):
        # Assuming that the types are as populated by the 'bootstrap'
        # migration.  This may need to change ...
        names = desktop_type_names()
        self.assertEqual(1, len(names))
        self.assertEqual('linux', names[0])

