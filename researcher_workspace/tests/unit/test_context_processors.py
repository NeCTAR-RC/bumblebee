from unittest.mock import patch

from django.test import TestCase, override_settings

from researcher_workspace.context_processors import from_settings


class FromSettingsTests(TestCase):

    def setUp(self):
        # Clear cached attrs from prior tests since the function caches
        # the env settings as function attributes.
        for attr in ('env_name', 'env_colour'):
            if hasattr(from_settings, attr):
                delattr(from_settings, attr)

    @override_settings(DEBUG=False)
    def test_production_overrides_to_hostname(self):
        # In production mode the function unconditionally derives the
        # env name from the hostname (any ENVIRONMENT_NAME setting is
        # discarded by design).
        with patch('researcher_workspace.context_processors.socket') \
                as mock_socket:
            mock_socket.gethostname.return_value = "prodhost"
            result = from_settings(request=None)
        self.assertEqual("Production on prodhost", result["ENVIRONMENT_NAME"])
        self.assertEqual("red", result["ENVIRONMENT_COLOR"])

    @override_settings(DEBUG=True, ENVIRONMENT_NAME="staging",
                       ENVIRONMENT_COLOR="blue")
    def test_debug_with_settings_provided(self):
        result = from_settings(request=None)
        self.assertEqual("staging", result["ENVIRONMENT_NAME"])
        self.assertEqual("blue", result["ENVIRONMENT_COLOR"])

    @override_settings(DEBUG=True, ENVIRONMENT_NAME=None,
                       ENVIRONMENT_COLOR=None)
    def test_debug_falls_back_to_hostname_and_green(self):
        with patch('researcher_workspace.context_processors.socket') \
                as mock_socket:
            mock_socket.gethostname.return_value = "devhost"
            result = from_settings(request=None)
        self.assertIn("Developing on", result["ENVIRONMENT_NAME"])
        self.assertEqual("green", result["ENVIRONMENT_COLOR"])

    def test_caches_result(self):
        with patch('researcher_workspace.context_processors.socket') \
                as mock_socket:
            mock_socket.gethostname.return_value = "h1"
            from_settings(request=None)
            mock_socket.gethostname.return_value = "h2"
            second = from_settings(request=None)
        # second call uses cached value (no re-read)
        self.assertIn("h1", second["ENVIRONMENT_NAME"])
