import base64
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from researcher_workspace.middleware import (
    MetricsAuthMiddleware, TimezoneMiddleware,
)
from researcher_workspace.tests.factories import UserFactory


class TimezoneMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = MagicMock(return_value="response")
        self.middleware = TimezoneMiddleware(self.get_response)

    def test_no_user_attribute(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        result = self.middleware(request)
        self.assertEqual("response", result)
        self.get_response.assert_called_once_with(request)

    def test_user_with_profile_no_timezone(self):
        user = UserFactory.create()
        user.profile.timezone = ""
        user.profile.save()
        request = self.factory.get("/")
        request.user = user
        with patch.object(timezone, 'deactivate') as mock_deactivate:
            self.middleware(request)
            mock_deactivate.assert_called_once()

    def test_user_with_profile_timezone(self):
        user = UserFactory.create()
        user.profile.timezone = "Australia/Brisbane"
        user.profile.save()
        request = self.factory.get("/")
        request.user = user
        with patch.object(timezone, 'activate') as mock_activate:
            self.middleware(request)
            mock_activate.assert_called_once()

    def test_user_profile_does_not_exist(self):
        request = self.factory.get("/")
        user = MagicMock()
        # Make hasattr(user, 'profile') True but accessing profile raises
        type(user).profile = property(
            lambda self: (_ for _ in ()).throw(ObjectDoesNotExist()))
        request.user = user
        # should not raise
        self.middleware(request)


class MetricsAuthMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = MagicMock(return_value="ok-response")
        self.middleware = MetricsAuthMiddleware(self.get_response)

    def test_non_metrics_url_passes_through(self):
        request = self.factory.get("/home/")
        request.user = AnonymousUser()
        result = self.middleware(request)
        self.assertEqual("ok-response", result)

    def test_metrics_url_superuser_allowed(self):
        request = self.factory.get("/metrics")
        user = MagicMock()
        user.is_superuser = True
        request.user = user
        result = self.middleware(request)
        self.assertEqual("ok-response", result)

    @override_settings(METRICS_USERNAME="m_user", METRICS_PASSWORD="m_pass")
    def test_metrics_url_basic_auth_correct(self):
        token = base64.b64encode(b"m_user:m_pass").decode()
        request = self.factory.get(
            "/metrics", HTTP_AUTHORIZATION=f"Basic {token}")
        user = MagicMock()
        user.is_superuser = False
        request.user = user
        result = self.middleware(request)
        self.assertEqual("ok-response", result)

    @override_settings(METRICS_USERNAME="m_user", METRICS_PASSWORD="m_pass")
    def test_metrics_url_basic_auth_wrong(self):
        token = base64.b64encode(b"bad:bad").decode()
        request = self.factory.get(
            "/metrics", HTTP_AUTHORIZATION=f"Basic {token}")
        user = MagicMock()
        user.is_superuser = False
        request.user = user
        result = self.middleware(request)
        self.assertEqual(401, result.status_code)

    def test_metrics_url_no_auth_unauthorized(self):
        request = self.factory.get("/metrics")
        user = MagicMock()
        user.is_superuser = False
        request.user = user
        result = self.middleware(request)
        self.assertEqual(401, result.status_code)
