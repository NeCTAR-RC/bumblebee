from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from researcher_desktop.tests.factories import DesktopTypeFactory
from researcher_workspace.models import (
    AROWhitelist, Feature, FeatureOptions, Permission, PermissionRequest,
    Project,
)
from researcher_workspace.tests.factories import (
    FeatureFactory, ProjectFactory, UserFactory,
)
from researcher_workspace.views import (
    custom_page_error, custom_page_not_found, healthcheck, on_login,
    on_logout,
)


class SimpleViewTests(TestCase):

    def test_healthcheck(self):
        response = self.client.get(reverse("healthcheck"))
        self.assertEqual(200, response.status_code)
        self.assertEqual(b"OK", response.content)

    def test_login_fail(self):
        response = self.client.get(reverse("login_fail"))
        self.assertEqual(200, response.status_code)

    def test_about(self):
        response = self.client.get(reverse("about"))
        self.assertEqual(200, response.status_code)

    def test_index_anonymous(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(200, response.status_code)

    def test_custom_404(self):
        factory = RequestFactory()
        request = factory.get("/no/such/path")
        response = custom_page_not_found(request)
        self.assertEqual(200, response.status_code)

    def test_custom_500_with_exception(self):
        factory = RequestFactory()
        request = factory.get("/some/path")
        response = custom_page_error(request, Exception("boom"))
        self.assertEqual(200, response.status_code)

    def test_custom_500_without_exception(self):
        factory = RequestFactory()
        request = factory.get("/some/path")
        request.user = UserFactory.create()
        response = custom_page_error(request)
        self.assertEqual(200, response.status_code)


class IndexAuthenticatedTest(TestCase):
    def test_index_authenticated_redirects_home(self):
        from django.conf import settings as conf
        user = UserFactory.create()
        user.terms_version = conf.TERMS_VERSION
        user.save()
        self.client.force_login(user)
        response = self.client.get(reverse("index"))
        # redirected to /home
        self.assertEqual(302, response.status_code)


class LoginLogoutSignalTests(TestCase):
    def test_on_login_signal_handler_with_user(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = UserFactory.create(first_name="Bob")
        # Add session/messages middleware-like attrs for messages.info
        from django.contrib.messages.storage.fallback import FallbackStorage
        from importlib import import_module
        from django.conf import settings as conf
        engine = import_module(conf.SESSION_ENGINE)
        request.session = engine.SessionStore()
        request._messages = FallbackStorage(request)
        on_login(sender=None, user=request.user, request=request)
        # Should not raise

    def test_on_logout_signal_handler_with_user(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = UserFactory.create(first_name="Bob")
        from django.contrib.messages.storage.fallback import FallbackStorage
        from importlib import import_module
        from django.conf import settings as conf
        engine = import_module(conf.SESSION_ENGINE)
        request.session = engine.SessionStore()
        request._messages = FallbackStorage(request)
        on_logout(sender=None, user=request.user, request=request)


class ProjectViewsTests(TestCase):

    def setUp(self):
        self.user = UserFactory.create()
        # Set terms accepted so user_passes_test passes
        from django.conf import settings as conf
        self.user.terms_version = conf.TERMS_VERSION
        self.user.save()
        self.feature = Feature.objects.get(app_name='researcher_desktop')

    @override_settings(LIMIT_WORKSPACES_PER_USER=1,
                       AUTO_APPROVE_WORKSPACES=True)
    def test_new_project_get(self):
        self.client.force_login(self.user)
        url = reverse("new_project")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)

    @override_settings(LIMIT_WORKSPACES_PER_USER=1,
                       AUTO_APPROVE_WORKSPACES=True)
    def test_new_project_get_at_limit(self):
        ProjectFactory.create(project_admin=self.user)
        self.client.force_login(self.user)
        response = self.client.get(reverse("new_project"))
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "")

    @override_settings(LIMIT_WORKSPACES_PER_USER=0,
                       AUTO_APPROVE_WORKSPACES=True)
    def test_new_project_post_auto_approved(self):
        self.client.force_login(self.user)
        url = reverse("new_project")
        response = self.client.post(url, data={
            'title': 'My Project',
            'description': 'My Desc',
            'FoR_code': '4602',
            'chief_investigator': 'ci@example.com',
        })
        self.assertEqual(302, response.status_code)
        self.assertEqual(1, Project.objects.filter(
            project_admin=self.user).count())
        proj = Project.objects.get(project_admin=self.user)
        self.assertTrue(proj.ARO_approval)

    @override_settings(LIMIT_WORKSPACES_PER_USER=0,
                       AUTO_APPROVE_WORKSPACES=False)
    def test_new_project_post_needs_approval(self):
        self.client.force_login(self.user)
        url = reverse("new_project")
        response = self.client.post(url, data={
            'title': 'My Project',
            'description': 'desc',
            'FoR_code': '4602',
            'chief_investigator': 'ci@example.com',
        })
        self.assertEqual(302, response.status_code)
        proj = Project.objects.get(project_admin=self.user)
        self.assertIsNone(proj.ARO_approval)

    @override_settings(LIMIT_WORKSPACES_PER_USER=0)
    def test_projects_list(self):
        ProjectFactory.create(project_admin=self.user)
        self.client.force_login(self.user)
        response = self.client.get(reverse("projects"))
        self.assertEqual(200, response.status_code)

    def test_project_edit_get(self):
        project = ProjectFactory.create(
            project_admin=self.user, FoR_code='4602',
            chief_investigator='ci@example.com')
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("project_edit", kwargs={'project_id': project.id}))
        self.assertEqual(200, response.status_code)

    def test_project_edit_post(self):
        project = ProjectFactory.create(
            project_admin=self.user, FoR_code='4602',
            chief_investigator='ci@example.com')
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("project_edit", kwargs={'project_id': project.id}),
            data={
                'title': 'New Title', 'description': 'd',
                'FoR_code': '4602', 'chief_investigator': 'ci@example.com'})
        self.assertEqual(302, response.status_code)
        project.refresh_from_db()
        self.assertEqual("New Title", project.title)


class StaffOnlyViewsTests(TestCase):
    def setUp(self):
        self.staff = UserFactory.create(is_staff=True)
        self.normal = UserFactory.create()
        from django.conf import settings as conf
        self.staff.terms_version = conf.TERMS_VERSION
        self.staff.save()
        self.normal.terms_version = conf.TERMS_VERSION
        self.normal.save()

    def test_staff_home_as_support_staff(self):
        # not_support_staff() returns True for non-Support-Staff group; the
        # view raises 404 in that case. Add the group.
        group, _ = Group.objects.get_or_create(name='Support Staff')
        self.normal.groups.add(group)
        self.client.force_login(self.normal)
        response = self.client.get(reverse("staff_home"))
        self.assertEqual(200, response.status_code)

    def test_staff_home_normal_user_404_handler(self):
        # The view raises Http404; handler404 renders the 404 template
        # but the existing custom_page_not_found returns status 200.
        self.client.force_login(self.normal)
        response = self.client.get(reverse("staff_home"))
        self.assertTemplateUsed(response, "researcher_workspace/404.html")

    def test_user_search_normal_user_404(self):
        self.client.force_login(self.normal)
        response = self.client.get(reverse("user_search"))
        self.assertEqual(200, response.status_code)
        # responds with 404 page rendered by custom_page_not_found

    def test_user_search_get_as_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("user_search"))
        self.assertEqual(200, response.status_code)

    def test_user_search_query(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("user_search"), data={'uid': 'someone'})
        self.assertEqual(200, response.status_code)

    def test_user_search_post_csv(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("user_search"))
        self.assertEqual(200, response.status_code)
        self.assertIn("text/csv", response['Content-Type'])
        self.assertIn("Orion_User_Report.csv",
                      response['Content-Disposition'])

    def test_user_search_details_get(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("user_search_details",
                    kwargs={'username': self.normal.username}))
        self.assertEqual(200, response.status_code)

    def test_user_search_details_post_add(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("user_search_details",
                    kwargs={'username': "added@x.com"}),
            data={'add_or_delete': 'add', 'aro_whitelist_comment': 'why not'})
        self.assertEqual(200, response.status_code)
        self.assertTrue(
            AROWhitelist.objects.filter(username="added@x.com").exists())

    def test_user_search_details_post_delete(self):
        AROWhitelist.objects.create(
            username="rem@x.com", permission_granted_by=self.staff)
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("user_search_details",
                    kwargs={'username': "rem@x.com"}),
            data={'add_or_delete': 'delete'})
        self.assertEqual(200, response.status_code)
        self.assertFalse(
            AROWhitelist.objects.filter(username="rem@x.com").exists())

    def test_user_search_details_normal_user_404(self):
        self.client.force_login(self.normal)
        response = self.client.get(
            reverse("user_search_details",
                    kwargs={'username': "x"}))
        self.assertEqual(200, response.status_code)


class HomeViewTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        from django.conf import settings as conf
        self.user.terms_version = conf.TERMS_VERSION
        self.user.save()

    def test_home_no_projects(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(200, response.status_code)

    def test_home_with_project(self):
        feature = Feature.objects.get(app_name='researcher_desktop')
        project = ProjectFactory.create(
            project_admin=self.user, ARO_approval=True)
        Permission.objects.create(project=project, feature=feature)
        self.user.profile.set_last_selected_project(project)
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(200, response.status_code)

    def test_home_post_select_project(self):
        feature = Feature.objects.get(app_name='researcher_desktop')
        project1 = ProjectFactory.create(
            project_admin=self.user, ARO_approval=True)
        project2 = ProjectFactory.create(
            project_admin=self.user, ARO_approval=True)
        Permission.objects.create(project=project2, feature=feature)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("home"), data={'project': str(project2.id)})
        self.assertEqual(200, response.status_code)
        self.user.refresh_from_db()
        self.assertEqual(project2,
                         self.user.profile.last_selected_project)

    def test_home_post_unapproved_project(self):
        approved = ProjectFactory.create(
            project_admin=self.user, ARO_approval=True)
        denied = ProjectFactory.create(
            project_admin=self.user, ARO_approval=False)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("home"), data={'project': str(denied.id)})
        self.assertEqual(200, response.status_code)

    @override_settings(GENERAL_WARNING_MESSAGE="Heads up!")
    def test_home_with_warning_message(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(200, response.status_code)


class FeatureRequestTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        from django.conf import settings as conf
        self.user.terms_version = conf.TERMS_VERSION
        self.user.save()
        self.project = ProjectFactory.create(
            project_admin=self.user, ARO_approval=True)
        self.user.profile.set_last_selected_project(self.project)
        self.feature = FeatureFactory.create(
            app_name='myfeat', auto_approved=False)
        self.opt = FeatureOptions.objects.create(name="optA")
        self.feature.options.add(self.opt)

    def test_request_feature_access_post_creates_request(self):
        self.client.force_login(self.user)
        url = reverse("request_feature_access",
                      kwargs={'feature_app_name': 'myfeat'})
        response = self.client.post(
            url, data={'feature_options': [self.opt.id]})
        self.assertEqual(302, response.status_code)
        self.assertTrue(PermissionRequest.objects.filter(
            requesting_user=self.user, requested_feature=self.feature
        ).exists())

    def test_request_feature_access_get_does_nothing(self):
        self.client.force_login(self.user)
        url = reverse("request_feature_access",
                      kwargs={'feature_app_name': 'myfeat'})
        response = self.client.get(url)
        self.assertEqual(302, response.status_code)
        self.assertEqual(0, PermissionRequest.objects.count())

    def test_request_feature_access_auto_approved(self):
        self.feature.auto_approved = True
        self.feature.save()
        # remove options for this branch
        self.feature.options.clear()
        self.client.force_login(self.user)
        url = reverse("request_feature_access",
                      kwargs={'feature_app_name': 'myfeat'})
        response = self.client.post(url)
        self.assertEqual(302, response.status_code)
        pr = PermissionRequest.objects.get(
            requesting_user=self.user, requested_feature=self.feature)
        self.assertTrue(pr.accepted)

    def test_request_feature_access_existing_request(self):
        prev = PermissionRequest.objects.create(
            requesting_user=self.user, project=self.project,
            requested_feature=self.feature)
        self.client.force_login(self.user)
        url = reverse("request_feature_access",
                      kwargs={'feature_app_name': 'myfeat'})
        response = self.client.post(
            url, data={'feature_options': [self.opt.id]})
        self.assertEqual(302, response.status_code)
        # should not create a new request
        self.assertEqual(1, PermissionRequest.objects.count())


class DesktopDetailsTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        from django.conf import settings as conf
        self.user.terms_version = conf.TERMS_VERSION
        self.user.save()
        self.feature = Feature.objects.get(app_name='researcher_desktop')

    @patch('researcher_desktop.models.get_nectar')
    @patch('researcher_workspace.views.desktop_limit_check')
    def test_desktop_details(self, mock_limit_check, mock_get_nectar):
        mock_limit_check.return_value = False
        # Render of desktop_details touches DesktopType.default_flavor
        # which hits get_nectar(); return a fake flavor list.
        medium = MagicMock(vcpus=4, ram=4096, disk=20)
        medium.name = 'm3.medium'
        big = MagicMock(vcpus=16, ram=32768, disk=80)
        big.name = 'm3.xxlarge'
        mock_get_nectar.return_value.nova.flavors.list.return_value = [
            medium, big]
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("desktop_details",
                    kwargs={'desktop_name': 'ubuntu'}))
        self.assertEqual(200, response.status_code)


class OrionReportTests(TestCase):
    def setUp(self):
        self.staff = UserFactory.create(is_staff=True)
        self.normal = UserFactory.create()
        from django.conf import settings as conf
        self.staff.terms_version = conf.TERMS_VERSION
        self.staff.save()

    def test_orion_report_get(self):
        self.client.force_login(self.staff)
        with patch('researcher_desktop.views.rd_report_page') as mock_page:
            mock_page.return_value = {}
            response = self.client.get(reverse("orion_report"))
        self.assertEqual(200, response.status_code)

    def test_orion_report_normal_user_404_handler(self):
        self.client.force_login(self.normal)
        response = self.client.get(reverse("orion_report"))
        self.assertTemplateUsed(response, "researcher_workspace/404.html")


class ReportLearnTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        from django.conf import settings as conf
        self.user.terms_version = conf.TERMS_VERSION
        self.user.save()

    @patch('researcher_workspace.views.rdesk_views.rd_report_for_user')
    def test_report(self, mock_report):
        mock_report.return_value = {}
        self.client.force_login(self.user)
        response = self.client.get(reverse("report"))
        self.assertEqual(200, response.status_code)

    def test_learn(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("learn"))
        self.assertEqual(200, response.status_code)
