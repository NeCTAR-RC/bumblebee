from unittest.mock import patch
import uuid

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from researcher_desktop.models import DesktopType
from researcher_workspace.tests.factories import UserFactory


class MoreDesktopRequestTests(TestCase):

    def setUp(self):
        super().setUp()
        self.desktop_type = DesktopType.objects.get(id='ubuntu')
        self.user = UserFactory.create(terms_version=settings.TERMS_VERSION)

    @patch("researcher_desktop.views.vm_man_views.delete_shelved_vm")
    def test_delete_shelved_vm(self, mock_delete_shelved):
        url = reverse("researcher_desktop:delete_shelved_vm",
                      kwargs={'desktop': self.desktop_type.id})
        self.client.force_login(self.user)
        response = self.client.get(url)
        mock_delete_shelved.assert_called_once_with(self.user,
                                                    self.desktop_type)
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)

    @patch("researcher_desktop.views.vm_man_views.extend_vm")
    def test_extend(self, mock_extend):
        vm_id = uuid.uuid4()
        url = reverse("researcher_desktop:extend",
                      kwargs={'vm_id': vm_id})
        self.client.force_login(self.user)
        response = self.client.get(url)
        mock_extend.assert_called_once()
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)

    @patch("researcher_desktop.views.vm_man_views.extend_boost_vm")
    def test_extend_boost(self, mock_extend):
        vm_id = uuid.uuid4()
        url = reverse("researcher_desktop:extend_boost",
                      kwargs={'vm_id': vm_id})
        self.client.force_login(self.user)
        response = self.client.get(url)
        mock_extend.assert_called_once()
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)

    @patch("researcher_desktop.views.vm_man_views.notify_vm")
    def test_notify_vm(self, mock_notify):
        mock_notify.return_value = "ok"
        url = reverse("researcher_desktop:notify_vm")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        mock_notify.assert_called_once()

    @patch("researcher_desktop.views.vm_man_views.phone_home")
    def test_phone_home(self, mock_phone_home):
        mock_phone_home.return_value = "ok"
        url = reverse("researcher_desktop:phone_home")
        response = self.client.post(url)
        self.assertEqual(200, response.status_code)
        mock_phone_home.assert_called_once()

    @patch("researcher_desktop.views.vm_man_views.get_vm_status")
    def test_status_vm(self, mock_status):
        mock_status.return_value = {'state': 'OK'}
        url = reverse("researcher_desktop:status_vm",
                      kwargs={'desktop': self.desktop_type.id})
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual({'state': 'OK'}, response.json())


class RDReportFunctionsTests(TestCase):
    @patch("researcher_desktop.views.vm_man_views.vm_report_for_csv")
    def test_rd_report(self, mock_csv):
        mock_csv.return_value = []
        from researcher_desktop.views import rd_report
        result = rd_report(6)
        self.assertEqual([], result)
        mock_csv.assert_called_once()

    @patch("researcher_desktop.views.vm_man_views.vm_report_for_page")
    def test_rd_report_page(self, mock_page):
        mock_page.return_value = {'vm_count': {}, 'vm_info': {}}
        from researcher_desktop.views import rd_report_page
        result = rd_report_page()
        self.assertIn('vm_count', result)
        self.assertIn('desktop_types', result)

    @patch("researcher_desktop.views.vm_man_views.rd_report_for_user")
    def test_rd_report_for_user(self, mock_for_user):
        mock_for_user.return_value = {'data': []}
        from researcher_desktop.views import rd_report_for_user
        user = UserFactory.create()
        result = rd_report_for_user(user)
        self.assertEqual({'data': []}, result)


class RenderModulesTests(TestCase):
    @patch("researcher_desktop.views.vm_man_views.render_vm")
    def test_render_modules(self, mock_render):
        mock_render.return_value = (None, None, None, None)
        from django.test import RequestFactory
        from researcher_desktop.views import render_modules
        factory = RequestFactory()
        request = factory.get("/")
        user = UserFactory.create()
        request.user = user
        result = render_modules(request)
        self.assertIsInstance(result, list)
