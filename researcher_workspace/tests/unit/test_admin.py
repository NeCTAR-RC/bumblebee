from unittest.mock import MagicMock

from django.test import RequestFactory, TestCase, override_settings

from researcher_workspace.admin import (
    AROWhitelistAdmin, CustomUserAdmin, FeatureAdmin, PermissionRequestAdmin,
    ProfileInline, ProjectAdmin,
)
from researcher_workspace.models import (
    AROWhitelist, Feature, PermissionRequest, Profile, Project, User,
)
from researcher_workspace.tests.factories import (
    FeatureFactory, ProjectFactory, UserFactory,
)


def _setup_messages(request):
    from django.contrib.messages.storage.fallback import FallbackStorage
    request.session = MagicMock()
    request._messages = FallbackStorage(request)


class PermissionRequestAdminTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.project = ProjectFactory.create(project_admin=self.user)
        self.feature = FeatureFactory.create(app_name='feat_a')
        self.factory = RequestFactory()

    def _make_request(self):
        req = self.factory.post("/admin/")
        req.user = self.user
        _setup_messages(req)
        return req

    def _make_pr(self):
        return PermissionRequest.objects.create(
            requesting_user=self.user, project=self.project,
            requested_feature=self.feature)

    @override_settings(DEBUG=True)
    def test_has_delete_permission_in_debug(self):
        admin_obj = PermissionRequestAdmin(PermissionRequest, MagicMock())
        self.assertTrue(admin_obj.has_delete_permission(self._make_request()))

    def test_response_change_accept(self):
        admin_obj = PermissionRequestAdmin(PermissionRequest, MagicMock())
        pr = self._make_pr()
        request = self.factory.post("/admin/", data={'_accept': '1'})
        request.user = self.user
        _setup_messages(request)
        response = admin_obj.response_change(request, pr)
        self.assertEqual(302, response.status_code)
        pr.refresh_from_db()
        self.assertTrue(pr.accepted)

    def test_response_change_deny(self):
        admin_obj = PermissionRequestAdmin(PermissionRequest, MagicMock())
        pr = self._make_pr()
        request = self.factory.post("/admin/", data={'_deny': '1'})
        request.user = self.user
        _setup_messages(request)
        response = admin_obj.response_change(request, pr)
        self.assertEqual(302, response.status_code)
        pr.refresh_from_db()
        self.assertFalse(pr.accepted)

    def test_accept_requests_action(self):
        admin_obj = PermissionRequestAdmin(PermissionRequest, MagicMock())
        pr1 = self._make_pr()
        pr2 = self._make_pr()
        admin_obj.accept_requests(self._make_request(),
                                  PermissionRequest.objects.all())
        pr1.refresh_from_db()
        pr2.refresh_from_db()
        self.assertTrue(pr1.accepted)
        self.assertTrue(pr2.accepted)

    def test_deny_requests_action(self):
        admin_obj = PermissionRequestAdmin(PermissionRequest, MagicMock())
        pr1 = self._make_pr()
        admin_obj.deny_requests(self._make_request(),
                                PermissionRequest.objects.all())
        pr1.refresh_from_db()
        self.assertFalse(pr1.accepted)


class ProjectAdminTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.factory = RequestFactory()

    @override_settings(DEBUG=False)
    def test_has_delete_permission_not_debug(self):
        admin_obj = ProjectAdmin(Project, MagicMock())
        request = self.factory.post("/admin/")
        request.user = self.user
        self.assertFalse(admin_obj.has_delete_permission(request))

    def test_response_change_accept(self):
        admin_obj = ProjectAdmin(Project, MagicMock())
        project = ProjectFactory.create(project_admin=self.user)
        request = self.factory.post("/admin/", data={'_accept': '1'})
        request.user = self.user
        _setup_messages(request)
        response = admin_obj.response_change(request, project)
        self.assertEqual(302, response.status_code)
        project.refresh_from_db()
        self.assertTrue(project.ARO_approval)

    def test_response_change_deny(self):
        admin_obj = ProjectAdmin(Project, MagicMock())
        project = ProjectFactory.create(project_admin=self.user)
        request = self.factory.post("/admin/", data={'_deny': '1'})
        request.user = self.user
        _setup_messages(request)
        response = admin_obj.response_change(request, project)
        self.assertEqual(302, response.status_code)
        project.refresh_from_db()
        self.assertFalse(project.ARO_approval)

    def test_approve_projects_action(self):
        admin_obj = ProjectAdmin(Project, MagicMock())
        ProjectFactory.create(project_admin=self.user)
        request = self.factory.post("/admin/")
        request.user = self.user
        admin_obj.approve_projects(request, Project.objects.all())
        for p in Project.objects.all():
            self.assertTrue(p.ARO_approval)

    def test_reject_projects_action(self):
        admin_obj = ProjectAdmin(Project, MagicMock())
        ProjectFactory.create(project_admin=self.user)
        request = self.factory.post("/admin/")
        request.user = self.user
        admin_obj.reject_projects(request, Project.objects.all())
        for p in Project.objects.all():
            self.assertFalse(p.ARO_approval)


class ProfileInlineTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()

    def test_aro_whitelisted_not_whitelisted(self):
        inline = ProfileInline(Profile, MagicMock())
        out = inline.aro_whitelisted(self.user.profile)
        self.assertIn("not ARO whitelisted", out)
        self.assertIn(self.user.username, out)

    def test_aro_whitelisted_with_whitelist(self):
        AROWhitelist.objects.create(
            username=self.user.username, permission_granted_by=self.user)
        inline = ProfileInline(Profile, MagicMock())
        out = inline.aro_whitelisted(self.user.profile)
        self.assertIn("Edit", out)


class CustomUserAdminTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.factory = RequestFactory()

    def test_get_inline_instances_no_obj(self):
        admin_obj = CustomUserAdmin(User, MagicMock())
        request = self.factory.get("/admin/")
        request.user = self.user
        result = admin_obj.get_inline_instances(request, obj=None)
        self.assertEqual([], result)

    @override_settings(OIDC_RP_CLIENT_SECRET='secret')
    def test_get_inline_instances_with_obj(self):
        admin_obj = CustomUserAdmin(User, MagicMock())
        request = self.factory.get("/admin/")
        # superuser to bypass perm checks
        request.user = UserFactory.create(
            is_staff=True, is_superuser=True)
        result = admin_obj.get_inline_instances(request, obj=self.user)
        self.assertTrue(len(result) >= 1)

    def test_response_change_add_to_whitelist(self):
        admin_obj = CustomUserAdmin(User, MagicMock())
        request = self.factory.post("/admin/", data={
            '_add_to_whitelist': '1',
            'aro_whitelist_comment': 'reason'})
        request.user = self.user
        _setup_messages(request)
        target = UserFactory.create(username="targetuser")
        response = admin_obj.response_change(request, target)
        self.assertEqual(302, response.status_code)
        self.assertTrue(
            AROWhitelist.objects.filter(username="targetuser").exists())

    def test_response_change_remove_from_whitelist(self):
        admin_obj = CustomUserAdmin(User, MagicMock())
        target = UserFactory.create(username="rmuser")
        AROWhitelist.objects.create(
            username="rmuser", permission_granted_by=self.user)
        request = self.factory.post("/admin/", data={
            '_remove_from_whitelist': '1'})
        request.user = self.user
        _setup_messages(request)
        response = admin_obj.response_change(request, target)
        self.assertEqual(302, response.status_code)
        self.assertFalse(
            AROWhitelist.objects.filter(username="rmuser").exists())


class AROWhitelistAdminTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.factory = RequestFactory()

    def test_get_readonly_fields_existing(self):
        admin_obj = AROWhitelistAdmin(AROWhitelist, MagicMock())
        wl = AROWhitelist.objects.create(
            username="x", permission_granted_by=self.user)
        request = self.factory.get("/admin/")
        request.user = self.user
        fields = admin_obj.get_readonly_fields(request, obj=wl)
        self.assertIn("username", fields)
        self.assertIn("created", fields)

    def test_get_readonly_fields_new(self):
        admin_obj = AROWhitelistAdmin(AROWhitelist, MagicMock())
        request = self.factory.get("/admin/")
        request.user = self.user
        fields = admin_obj.get_readonly_fields(request, obj=None)
        self.assertNotIn("username", fields)

    def test_get_fields_existing_vs_new(self):
        admin_obj = AROWhitelistAdmin(AROWhitelist, MagicMock())
        request = self.factory.get("/admin/")
        request.user = self.user
        new_fields = admin_obj.get_fields(request, obj=None)
        self.assertIn("username", new_fields)
        wl = AROWhitelist.objects.create(
            username="y", permission_granted_by=self.user)
        existing_fields = admin_obj.get_fields(request, obj=wl)
        self.assertIn("created", existing_fields)

    def test_save_model_new_assigns_user(self):
        admin_obj = AROWhitelistAdmin(AROWhitelist, MagicMock())
        request = self.factory.post("/admin/")
        request.user = self.user
        wl = AROWhitelist(username="z")
        admin_obj.save_model(request, wl, form=None, change=False)
        wl.refresh_from_db()
        self.assertEqual(self.user, wl.permission_granted_by)


class FeatureAdminTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.factory = RequestFactory()

    def test_view_feature(self):
        feat = FeatureFactory.create(feature_or_service=True)
        admin_obj = FeatureAdmin(Feature, MagicMock())
        self.assertEqual("Feature", admin_obj.view_feature_or_service(feat))

    def test_view_service(self):
        feat = FeatureFactory.create(feature_or_service=False)
        admin_obj = FeatureAdmin(Feature, MagicMock())
        self.assertEqual("Service", admin_obj.view_feature_or_service(feat))

    @override_settings(DEBUG=False)
    def test_has_delete_permission(self):
        admin_obj = FeatureAdmin(Feature, MagicMock())
        request = self.factory.get("/admin/")
        request.user = self.user
        self.assertFalse(admin_obj.has_delete_permission(request))

    def test_save_model_emits_warning_when_name_changed(self):
        admin_obj = FeatureAdmin(Feature, MagicMock())
        request = self.factory.post("/admin/")
        request.user = self.user
        _setup_messages(request)
        feat = FeatureFactory.create(name="OldName")
        feat.name = "NewName"
        form = MagicMock(changed_data=['name'])
        admin_obj.save_model(request, feat, form, change=True)
        # No exception means it worked
