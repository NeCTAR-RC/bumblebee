import os
from unittest import mock

from django.test import SimpleTestCase

from researcher_workspace import sentry


DSN = 'https://key@glitchtip.example.com/1'
RELEASE = 'bumblebee@1.0.0'


@mock.patch('researcher_workspace.sentry._release', return_value=RELEASE)
@mock.patch('researcher_workspace.sentry.sentry_sdk')
class SentrySetupTests(SimpleTestCase):
    def test_setup_no_dsn(self, mock_sdk, mock_release):
        with mock.patch.dict(os.environ):
            os.environ.pop('SENTRY_DSN', None)
            self.assertFalse(sentry.setup())
        mock_sdk.init.assert_not_called()

    def test_setup_with_dsn_and_environment(self, mock_sdk, mock_release):
        self.assertTrue(sentry.setup(DSN, 'testing'))
        mock_sdk.init.assert_called_once_with(
            dsn=DSN,
            environment='testing',
            release=RELEASE,
            auto_session_tracking=False,
        )

    def test_setup_dsn_only(self, mock_sdk, mock_release):
        self.assertTrue(sentry.setup(DSN))
        mock_sdk.init.assert_called_once_with(
            dsn=DSN,
            environment=None,
            release=RELEASE,
            auto_session_tracking=False,
        )

    def test_setup_dsn_from_environment(self, mock_sdk, mock_release):
        with mock.patch.dict(os.environ, {'SENTRY_DSN': DSN}):
            self.assertTrue(sentry.setup())
        mock_sdk.init.assert_called_once_with(
            dsn=DSN,
            environment=None,
            release=RELEASE,
            auto_session_tracking=False,
        )


class ReleaseTests(SimpleTestCase):
    def test_release(self):
        with mock.patch('researcher_workspace.sentry.pbr') as mock_pbr:
            version_info = mock_pbr.version.VersionInfo.return_value
            version_info.release_string.return_value = '1.2.3'
            self.assertEqual('bumblebee@1.2.3', sentry._release())

    def test_release_unknown(self):
        with mock.patch(
            'researcher_workspace.sentry.pbr.version.VersionInfo',
            side_effect=Exception('no version'),
        ):
            self.assertIsNone(sentry._release())
