from django.test import TestCase

from guacamole.models import GuacamoleUser, GuacamoleConnection
from guacamole.models import GuacamoleConnectionParameter
from guacamole.models import GuacamoleConnectionPermission
from guacamole.utils import quick_rdp, quick_rdp_destroy, get_connection_path

from guacamole.tests.factories import GuacamoleConnectionFactory


class SimpleTestCase(TestCase):
    """
    Simple test cases that verifies basic model functionality.
    """

    def test_get_connection_path(self):
        conn = GuacamoleConnectionFactory.create(connection_id=1)
        self.assertEqual(get_connection_path(conn), '#/client/MQBjAG15c3Fs')

        conn = GuacamoleConnectionFactory.create(connection_id=54)
        self.assertEqual(get_connection_path(conn), '#/client/NTQAYwBteXNxbA')

        conn = GuacamoleConnectionFactory.create(connection_id=156)
        self.assertEqual(get_connection_path(conn), '#/client/MTU2AGMAbXlzcWw')

        conn = GuacamoleConnectionFactory.create(connection_id=1234)
        self.assertEqual(get_connection_path(conn), '#/client/MTIzNABjAG15c3Fs')

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

        self.assertEqual(gcp.entity.name, "guacman")
        self.assertEqual(gcp.connection.protocol, "rdp")
        self.assertEqual(gcp.permission, "READ")

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

        self.assertEqual(
            hostname_parameter.parameter_value,
            'some.windows.host')

        self.assertEqual(
            username_parameter.parameter_value,
            'Administrator')

        self.assertEqual(
            password_parameter.parameter_value,
            'passwerd')

        quick_rdp_destroy(
            guac_username="guacman",
            username="Administrator",
            hostname="some.windows.host")

        # We should be empty now
        self.assertEqual(GuacamoleUser.objects.count(), 0)
        self.assertEqual(GuacamoleConnection.objects.count(), 0)
        self.assertEqual(GuacamoleConnectionPermission.objects.count(), 0)
