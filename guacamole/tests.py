from django.test import TestCase

from guacamole.models import GuacamoleUser, GuacamoleConnection
from guacamole.models import GuacamoleConnectionPermission
from guacamole.utils import quick_rdp, quick_rdp_destroy


class SimpleTestCase(TestCase):
    """
    Simple test cases that verifies basic model functionality.
    """

    def test_quick_rdp(self):
        """
        Test utility method quick_rdp; will exercise models: User, Connection,
        ConnectionParameter, ConnectionPermission, as well other utility
        methods quick_rdp_conn and quick_guac_user.
        """

        # Get a GuacamoleConnectionPermission back.  We can then inspect the
        # Connection and User
        gcp = quick_rdp(
            guac_username="guacman",
            guac_password="avocado",
            username="Administrator",
            password="passwerd",
            hostname="some.windows.host")

        self.assertEquals(gcp.entity.name, "guacman")
        self.assertEquals(gcp.connection.protocol, "rdp")
        self.assertEquals(gcp.permission, "READ")

        hostname_parameter = gcp.connection.parameters.get(
            parameter_name='hostname')

        username_parameter = gcp.connection.parameters.get(
            parameter_name='username')

        password_parameter = gcp.connection.parameters.get(
            parameter_name='password')

        self.assertEquals(
            hostname_parameter.parameter_value,
            'some.windows.host')

        self.assertEquals(
            username_parameter.parameter_value,
            'Administrator')

        self.assertEquals(
            password_parameter.parameter_value,
            'passwerd')

        quick_rdp_destroy(
            guac_username="guacman",
            username="Administrator",
            hostname="some.windows.host")

        # We should be empty now
        self.assertEquals(GuacamoleUser.objects.count(), 0)
        self.assertEquals(GuacamoleConnection.objects.count(), 0)
        self.assertEquals(GuacamoleConnectionPermission.objects.count(), 0)
