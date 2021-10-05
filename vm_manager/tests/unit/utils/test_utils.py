from unittest.mock import Mock, patch

from django.test import TestCase
from django.conf import settings

from vm_manager.utils.utils import generate_server_name, generate_hostname, \
    generate_hostname_url, get_domain


class UtilTests(TestCase):

    def test_generators(self):
        self.assertEqual(f"ubuntu_fred_{settings.ENVIRONMENT_NAME[0]}",
                         generate_server_name('fred', 'ubuntu'))
        self.assertEqual("rdu-fnoord",
                         generate_hostname_url('fnoord', 'ubuntu'))
        self.assertEqual("rdu-fnoord",
                         generate_hostname('fnoord', 'ubuntu'))
        self.assertEqual("test", get_domain('fred'))
