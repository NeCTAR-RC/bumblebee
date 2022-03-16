from unittest.mock import patch
import uuid

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from researcher_workspace.tests.factories import UserFactory

from researcher_desktop.models import DesktopType, AvailabilityZone
from researcher_desktop.utils.utils import desktops_feature


class DesktopRequestTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.desktop_type = DesktopType.objects.get(id='ubuntu')
        self.qriscloud = AvailabilityZone.objects.get(name='QRIScloud')
        self.qriscloud.network_id = uuid.uuid4()
        self.qriscloud.save()
        self.melbourne = AvailabilityZone.objects.get(name='melbourne-qh2')
        self.melbourne.network_id = uuid.uuid4()
        self.melbourne.save()
        self.user = UserFactory.create(terms_version=settings.TERMS_VERSION)
        self.feature = desktops_feature()

    @patch("researcher_desktop.views.vm_man_views.launch_vm")
    def test_launch_vm_auth(self, mock_launch_vm):
        # with the AnonymousUser
        url = reverse("researcher_desktop:launch_vm_default",
                    kwargs={'desktop': 'ubuntu'})
        response = self.client.get(url)
        mock_launch_vm.assert_not_called()
        self.assertRedirects(response, f"/login/?next={url}",
                             fetch_redirect_response=False)

        # with a User with no terms_version
        user = UserFactory.create(terms_version=0)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_launch_vm.assert_not_called()
        self.assertRedirects(response, reverse("terms"),
                             fetch_redirect_response=False)

        # with a User with the current terms_version
        user = UserFactory.create(terms_version=settings.TERMS_VERSION)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_launch_vm.assert_called_once()
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)

    @patch("researcher_desktop.views.vm_man_views.launch_vm")
    def test_launch_vm_default_zone(self, mock_launch_vm):
        url = reverse("researcher_desktop:launch_vm_default",
                    kwargs={'desktop': self.desktop_type.id})
        self.client.force_login(self.user)
        response = self.client.get(url)
        mock_launch_vm.assert_called_once_with(
            self.user, self.desktop_type, self.qriscloud)
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)

    @patch("researcher_desktop.views.vm_man_views.launch_vm")
    def test_launch_vm_bogus_zone(self, mock_launch_vm):
        url = reverse("researcher_desktop:launch_vm",
                    kwargs={'desktop': self.desktop_type.id,
                            'zone_name': 'bogus'})
        self.client.force_login(self.user)
        response = self.client.get(url)
        mock_launch_vm.assert_not_called()
        self.assertEqual(200, response.status_code)

    @patch("researcher_desktop.views.vm_man_views.launch_vm")
    def test_launch_vm_given_zone(self, mock_launch_vm):
        url = reverse("researcher_desktop:launch_vm",
                    kwargs={'desktop': self.desktop_type.id,
                            'zone_name': 'melbourne-qh2'})
        self.client.force_login(self.user)
        response = self.client.get(url)
        mock_launch_vm.assert_called_once_with(
            self.user, self.desktop_type, self.melbourne)
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)

    @patch("researcher_desktop.views.vm_man_views.launch_vm")
    def test_launch_vm_bogus_dt(self, mock_launch_vm):
        url = reverse("researcher_desktop:launch_vm",
                    kwargs={'desktop': 'windoze',
                            'zone_name': 'melbourne-qh2'})
        self.client.force_login(self.user)
        response = self.client.get(url)
        mock_launch_vm.assert_not_called()
        self.assertEqual(200, response.status_code)

    @patch("researcher_desktop.views.vm_man_views.delete_vm")
    def test_delete_vm(self, mock_delete_vm):
        vm_id = uuid.uuid4()
        # with the AnonymousUser
        url = reverse("researcher_desktop:delete_vm", kwargs={'vm_id': vm_id})
        response = self.client.get(url)
        mock_delete_vm.assert_not_called()
        self.assertRedirects(response, f"/login/?next={url}",
                             fetch_redirect_response=False)

        # with a User with no terms_version
        user = UserFactory.create(terms_version=0)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_delete_vm.assert_not_called()
        self.assertRedirects(response, reverse("terms"),
                             fetch_redirect_response=False)

        # with a User with the current terms_version
        user = UserFactory.create(terms_version=settings.TERMS_VERSION)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_delete_vm.assert_called_once_with(user, vm_id, self.feature)
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)

    @patch("researcher_desktop.views.vm_man_views.shelve_vm")
    def test_shelve_vm(self, mock_shelve_vm):
        vm_id = uuid.uuid4()
        # with the AnonymousUser
        url = reverse("researcher_desktop:shelve_vm", kwargs={'vm_id': vm_id})
        response = self.client.get(url)
        mock_shelve_vm.assert_not_called()
        self.assertRedirects(response, f"/login/?next={url}",
                             fetch_redirect_response=False)

        # with a User with no terms_version
        user = UserFactory.create(terms_version=0)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_shelve_vm.assert_not_called()
        self.assertRedirects(response, reverse("terms"),
                             fetch_redirect_response=False)

        # with a User with the current terms_version
        user = UserFactory.create(terms_version=settings.TERMS_VERSION)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_shelve_vm.assert_called_once_with(user, vm_id, self.feature)
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)

    @patch("researcher_desktop.views.vm_man_views.supersize_vm")
    def test_supersize_vm(self, mock_supersize_vm):
        vm_id = uuid.uuid4()
        # with the AnonymousUser
        url = reverse("researcher_desktop:supersize_vm",
                      kwargs={'vm_id': vm_id})
        response = self.client.get(url)
        mock_supersize_vm.assert_not_called()
        self.assertRedirects(response, f"/login/?next={url}",
                             fetch_redirect_response=False)

        # with a User with no terms_version
        user = UserFactory.create(terms_version=0)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_supersize_vm.assert_not_called()
        self.assertRedirects(response, reverse("terms"),
                             fetch_redirect_response=False)

        # with a User with the current terms_version
        user = UserFactory.create(terms_version=settings.TERMS_VERSION)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_supersize_vm.assert_called_once_with(user, vm_id, self.feature)
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)

    @patch("researcher_desktop.views.vm_man_views.downsize_vm")
    def test_downsize_vm(self, mock_downsize_vm):
        vm_id = uuid.uuid4()
        # with the AnonymousUser
        url = reverse("researcher_desktop:downsize_vm",
                      kwargs={'vm_id': vm_id})
        response = self.client.get(url)
        mock_downsize_vm.assert_not_called()
        self.assertRedirects(response, f"/login/?next={url}",
                             fetch_redirect_response=False)

        # with a User with no terms_version
        user = UserFactory.create(terms_version=0)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_downsize_vm.assert_not_called()
        self.assertRedirects(response, reverse("terms"),
                             fetch_redirect_response=False)

        # with a User with the current terms_version
        user = UserFactory.create(terms_version=settings.TERMS_VERSION)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_downsize_vm.assert_called_once_with(user, vm_id, self.feature)
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)

    @patch("researcher_desktop.views.vm_man_views.unshelve_vm")
    def test_unshelve_vm(self, mock_unshelve_vm):
        vm_id = uuid.uuid4()
        # with the AnonymousUser
        url = reverse("researcher_desktop:unshelve_vm",
                      kwargs={'desktop': self.desktop_type.id})
        response = self.client.get(url)
        mock_unshelve_vm.assert_not_called()
        self.assertRedirects(response, f"/login/?next={url}",
                             fetch_redirect_response=False)

        # with a User with no terms_version
        user = UserFactory.create(terms_version=0)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_unshelve_vm.assert_not_called()
        self.assertRedirects(response, reverse("terms"),
                             fetch_redirect_response=False)

        # with a User with the current terms_version
        user = UserFactory.create(terms_version=settings.TERMS_VERSION)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_unshelve_vm.assert_called_once_with(user, self.desktop_type)
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)

    @patch("researcher_desktop.views.vm_man_views.reboot_vm")
    def test_reboot_vm(self, mock_reboot_vm):
        vm_id = uuid.uuid4()
        # with the AnonymousUser
        url = reverse("researcher_desktop:reboot_vm",
                      kwargs={'vm_id': vm_id, 'reboot_level': 'HARD'})
        response = self.client.get(url)
        mock_reboot_vm.assert_not_called()
        self.assertRedirects(response, f"/login/?next={url}",
                             fetch_redirect_response=False)

        # with a User with no terms_version
        user = UserFactory.create(terms_version=0)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_reboot_vm.assert_not_called()
        self.assertRedirects(response, reverse("terms"),
                             fetch_redirect_response=False)

        # with a User with the current terms_version
        user = UserFactory.create(terms_version=settings.TERMS_VERSION)
        self.client.force_login(user)
        response = self.client.get(url)
        mock_reboot_vm.assert_called_once_with(user, vm_id, 'HARD',
                                               desktops_feature())
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)
