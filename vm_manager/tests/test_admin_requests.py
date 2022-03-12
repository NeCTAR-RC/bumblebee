from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from researcher_workspace.tests.factories import UserFactory


class VMManagerAdminRequestTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create(first_name="Luke",
                                       last_name="Sleepwalker")
        self.superuser = UserFactory.create(first_name="Slightly",
                                            last_name="Quickerman",
                                            is_superuser=True,
                                            is_staff=True)
        self.charset = settings.DEFAULT_CHARSET

    def test_access(self):
        url = reverse("admin:index")
        # with the AnonymousUser
        response = self.client.get(url)

        # FIXME - is this the correct place to redirect to?
        self.assertRedirects(response, f"/rcsadmin/login/?next={url}",
                             fetch_redirect_response=False)

        # as normal user
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertRedirects(response, f"/rcsadmin/login/?next={url}",
                             fetch_redirect_response=False)

        # as superuser
        self.client.force_login(self.superuser)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
