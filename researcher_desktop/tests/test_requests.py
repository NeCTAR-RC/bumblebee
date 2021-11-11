import uuid
import copy
from datetime import datetime, timedelta, timezone

from unittest.mock import Mock, patch, call

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import Http404, HttpResponseRedirect
from django.test import TestCase
from django.urls import reverse

from researcher_workspace.tests.factories import FeatureFactory, UserFactory

from researcher_workspace.models import User
from researcher_desktop.views import launch_vm


class DesktopRequestTests(TestCase):
    # TODO - I don't get why I don't need to prefix the url_paths with
    # 'researcher_desktop:'.  But when I do the reverse(...) calls fail.

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()

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
        self.client.force_login(self.user)
        response = self.client.get(url)
        mock_launch_vm.assert_not_called()
        self.assertRedirects(response, reverse("terms"),
                             fetch_redirect_response=False)

        # with a User with the current terms_version
        self.user.terms_version = settings.TERMS_VERSION
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.get(url)
        mock_launch_vm.assert_called_once()
        self.assertRedirects(response, reverse("home"),
                             fetch_redirect_response=False)
