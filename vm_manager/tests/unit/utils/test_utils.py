from django.test import TestCase

from vm_manager.utils.utils import generate_server_name, generate_hostname, \
    get_domain


class UtilTests(TestCase):

    def test_generators(self):
        self.assertEqual("fred_ubuntu",
                         generate_server_name('fred', 'ubuntu'))
        self.assertEqual("vdu-fnoord",
                         generate_hostname('fnoord', 'ubuntu'))
        self.assertEqual("test", get_domain('fred'))
