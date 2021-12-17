import uuid
import copy
from datetime import datetime, timedelta, timezone

from unittest.mock import Mock, patch, call

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import Http404, HttpResponseRedirect
from django.test import TestCase
from django.urls import reverse

from researcher_workspace.tests.factories import FeatureFactory, UserFactory, \
    ProfileFactory

from researcher_workspace.models import User, Profile
from researcher_workspace.views import terms, agree_terms


class ResearcherWorkspaceRequestTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create(first_name="Luke",
                                       last_name="Sleepwalker")
        self.charset = settings.DEFAULT_CHARSET

    def test_terms(self):
        # with the AnonymousUser
        response = self.client.get(reverse("terms"))
        self.assertFalse(response.context['show_agree'])
        self.assertEqual(settings.TERMS_VERSION,
                         response.context['version'])
        self.assertEqual(200, response.status_code)

        # with a User with no terms_version
        self.client.force_login(self.user)
        response = self.client.get(reverse("terms"))
        self.assertTrue(response.context['show_agree'])
        self.assertEqual(settings.TERMS_VERSION,
                         response.context['version'])
        self.assertEqual(200, response.status_code)

        # with a User with the current terms_version
        self.user.terms_version = settings.TERMS_VERSION
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse("terms"))
        self.assertFalse(response.context['show_agree'])
        self.assertEqual(settings.TERMS_VERSION,
                         response.context['version'])
        self.assertEqual(200, response.status_code)

    def test_agree_terms(self):
        url_version_zero = reverse("agree_terms", kwargs={'version': 0})
        url_version_right = reverse("agree_terms",
                                    kwargs={'version': settings.TERMS_VERSION})

        # with Anonymous User
        response = self.client.post(url_version_right)
        self.assertEqual(400, response.status_code)

        # with real user
        self.client.force_login(self.user)

        # get not post
        response = self.client.get(url_version_right)
        self.assertEqual(400, response.status_code)
        user = User.objects.get(pk=self.user.pk)
        self.assertEqual(0, user.terms_version)
        self.assertIsNone(user.date_agreed_terms)

        # post wrong version
        response = self.client.post(url_version_zero)
        self.assertEqual(200, response.status_code)
        user = User.objects.get(pk=self.user.pk)
        self.assertEqual(0, user.terms_version)
        self.assertIsNone(user.date_agreed_terms)

        # post correct version
        response = self.client.post(url_version_right)
        self.assertEqual(200, response.status_code)
        user = User.objects.get(pk=self.user.pk)
        self.assertEqual(settings.TERMS_VERSION, user.terms_version)
        self.assertIsNotNone(user.date_agreed_terms)

    def test_profile(self):
        # with the AnonymousUser
        url = reverse("profile")
        response = self.client.get(url)
        self.assertRedirects(response, f"/login/?next={url}",
                             fetch_redirect_response=False)

        # with real user
        self.user.profile.timezone = "Australia/Brisbane"
        self.user.profile.save()
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("Australia/Brisbane",
                         response.context['form'].initial['timezone'])

    def test_profile_update(self):
        # with the AnonymousUser
        url = reverse("profile")
        response = self.client.post(
            url, data={'timezone': "Australia/Brisbane"})
        self.assertRedirects(response, f"/login/?next={url}",
                             fetch_redirect_response=False)

        # with real user
        self.user.profile.timezone = "Australia/Brisbane"
        self.user.profile.save()
        self.client.force_login(self.user)

        # invalid zone
        response = self.client.post(
            url, data={'timezone': "Australia/Kanmantoo"})
        self.assertEqual(200, response.status_code)
        self.assertIsNotNone(response.context['form'].errors)
        profile = Profile.objects.get(pk=self.user.profile.pk)
        self.assertEqual("Australia/Brisbane", profile.timezone)

        # valid zone
        response = self.client.post(
            url, data={'timezone': "Australia/Perth"})
        self.assertRedirects(response, "/home/",
                             fetch_redirect_response=False)
        profile = Profile.objects.get(pk=self.user.profile.pk)
        self.assertEqual("Australia/Perth", profile.timezone)

    def test_help(self):
        url = reverse("help")

        # with the AnonymousUser
        response = self.client.get(url)
        self.assertRedirects(response, f"/login/?next={url}",
                             fetch_redirect_response=False)

        # with real user
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        # match the user's email in the form
        self.assertTrue(response.content.find(
            bytes(f'value="{self.user.email}"', self.charset)) >= 0)

    @patch('researcher_workspace.views.create_ticket')
    @patch('researcher_workspace.views.messages')
    def test_post_help_request(self, mock_messages, mock_create_ticket):
        url = reverse("help")
        params = {'message': "1\n2\n3"}

        # with the AnonymousUser
        response = self.client.post(url, params)
        self.assertRedirects(response, f"/login/?next={url}",
                             fetch_redirect_response=False)

        # with real user
        mock_create_ticket.return_value = 1234
        self.client.force_login(self.user)
        response = self.client.post(url, params)
        self.assertRedirects(response, url, fetch_redirect_response=False)
        mock_create_ticket.assert_called_once_with(
            name="Luke Sleepwalker", email=self.user.email,
            subject="Virtual Desktop support request",
            description="1<br/>2<br/>3",
            tags=["Virtual Desktop"]
        )
        mock_messages.success.assert_called_once()
        mock_messages.error.assert_not_called()

        params = {'message': '123', 'subject': 'to be announced'}
        mock_messages.success.reset_mock()
        mock_messages.error.reset_mock()
        mock_create_ticket.reset_mock()
        response = self.client.post(url, params)
        self.assertRedirects(response, url, fetch_redirect_response=False)
        mock_create_ticket.assert_called_once_with(
            name="Luke Sleepwalker", email=self.user.email,
            subject="to be announced",
            description="123",
            tags=["Virtual Desktop"]
        )
        mock_messages.success.assert_called_once()
        mock_messages.error.assert_not_called()

        params = {'message': '', 'subject': 'to be announced'}
        mock_messages.success.reset_mock()
        mock_messages.error.reset_mock()
        mock_create_ticket.reset_mock()
        response = self.client.post(url, params)
        self.assertEqual(200, response.status_code)
        mock_create_ticket.assert_not_called()
        mock_messages.success.assert_not_called()
        mock_messages.error.assert_not_called()

        # simulate ticket submission failures
        params = {'message': "1\n2\n3"}
        mock_messages.success.reset_mock()
        mock_messages.error.reset_mock()
        mock_create_ticket.reset_mock()
        mock_create_ticket.return_value = None
        response = self.client.post(url, params)
        self.assertEqual(200, response.status_code)
        mock_create_ticket.assert_called_once()
        mock_messages.success.assert_not_called()
        mock_messages.error.assert_called_once()

        mock_messages.success.reset_mock()
        mock_messages.error.reset_mock()
        mock_create_ticket.reset_mock()
        mock_create_ticket.return_value = 1234
        mock_create_ticket.side_effect = Exception("something bad")
        response = self.client.post(url, params)
        self.assertEqual(200, response.status_code)
        mock_create_ticket.assert_called_once()
        mock_messages.success.assert_not_called()
        mock_messages.error.assert_called_once()
