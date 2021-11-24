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

from researcher_workspace.models import User
from researcher_workspace.views import terms, agree_terms


class ResearcherWorkspaceRequestTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()

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
        response = self.client.get(reverse("agree_terms",
                                           kwargs={'version': 0}))
        self.assertEqual(200, response.status_code)

        self.client.force_login(self.user)
        response = self.client.get(reverse("agree_terms",
                                           kwargs={'version': 0}))
        self.assertEqual(302, response.status_code)
        user = User.objects.get(pk=self.user.pk)
        self.assertEqual(0, user.terms_version)
        self.assertIsNone(user.date_agreed_terms)

        response = self.client.get(reverse(
            "agree_terms",
            kwargs={'version': settings.TERMS_VERSION}))
        self.assertEqual(302, response.status_code)
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
