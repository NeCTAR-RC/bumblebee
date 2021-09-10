from django.test import TestCase

from guacamole.models import GuacamoleUser, GuacamoleConnection
from guacamole.models import GuacamoleConnectionParameter
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

        def get_parameter(connection, name):
            try:
                return GuacamoleConnectionParameter.objects.filter(
                    connection=connection,
                    parameter_name=name).get()
            except GuacamoleConnectionParameter.DoesNotExist:
                return None

        hostname_parameter = get_parameter(gcp.connection, 'hostname')
        username_parameter = get_parameter(gcp.connection, 'username')
        password_parameter = get_parameter(gcp.connection, 'password')

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
