from django.conf import settings
from django.core import mail
from django.http import Http404
from django.test import TestCase

from researcher_workspace.models import (
    AROWhitelist, Feature, FeatureOptions, Permission, PermissionRequest,
    Profile, Project, add_username_to_whitelist,
    get_permission_feature_options_for_latest_project,
    remove_username_from_whitelist,
)
from researcher_workspace.tests.factories import (
    FeatureFactory, ProjectFactory, UserFactory,
)


class WorkspaceModelTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)

    def test_project_accept(self):
        user = UserFactory.create(email="test@test.test")
        project = ProjectFactory.create(project_admin=user)
        project.accept()
        self.assertTrue(project.ARO_approval)
        self.assertIsNotNone(project.ARO_responded_on)
        self.assertEqual(1, project.permissions.count())
        self.assertEqual('researcher_desktop',
                         project.permissions.first().app_name)
        self.assertEqual(1, len(mail.outbox))
        self.assertIn("approved", mail.outbox[0].subject)
        self.assertEqual(["test@test.test"],
                         mail.outbox[0].recipients())
        self.assertEqual(settings.DEFAULT_FROM_EMAIL,
                         mail.outbox[0].from_email)
        self.assertIn(project.title, mail.outbox[0].body)

        project = ProjectFactory.create(project_admin=user)
        project.accept(enable_default_features=False)
        self.assertTrue(project.ARO_approval)
        self.assertIsNotNone(project.ARO_responded_on)
        self.assertEqual(0, project.permissions.count())
        self.assertEqual(2, len(mail.outbox))

    def test_project_deny(self):
        user = UserFactory.create()
        project = ProjectFactory.create(project_admin=user)
        project.deny()
        self.assertFalse(project.ARO_approval)
        self.assertIsNotNone(project.ARO_responded_on)
        self.assertEqual(1, len(mail.outbox))
        self.assertIn("declined", mail.outbox[0].subject.lower())

    def test_project_str(self):
        user = UserFactory.create()
        project = ProjectFactory.create(project_admin=user, title="Foo")
        self.assertIn("Foo", str(project))


class FeatureManagerTests(TestCase):
    def test_get_existing_feature(self):
        feature = FeatureFactory.create(app_name="known_feature")
        user = UserFactory.create()
        result = Feature.objects.get_feature_by_untrusted_feature_name(
            "known_feature", user)
        self.assertEqual(feature, result)

    def test_get_missing_feature_raises_404(self):
        user = UserFactory.create()
        with self.assertRaises(Http404):
            Feature.objects.get_feature_by_untrusted_feature_name(
                "no_such_feature", user)

    def test_feature_str(self):
        feature = FeatureFactory.create(name="MyFeat")
        self.assertEqual("MyFeat", str(feature))


class FeatureOptionsTests(TestCase):
    def test_str(self):
        opt = FeatureOptions.objects.create(name="optX")
        self.assertEqual("optX", str(opt))


class ProjectManagerTests(TestCase):
    def test_get_existing_owned(self):
        user = UserFactory.create()
        project = ProjectFactory.create(project_admin=user)
        result = Project.objects.get_project_by_untrusted_project_id(
            project.id, user)
        self.assertEqual(project, result)

    def test_get_value_error_raises_404(self):
        user = UserFactory.create()
        with self.assertRaises(Http404):
            Project.objects.get_project_by_untrusted_project_id(
                "not-a-number", user)

    def test_get_missing_raises_404(self):
        user = UserFactory.create()
        with self.assertRaises(Http404):
            Project.objects.get_project_by_untrusted_project_id(99999, user)

    def test_get_other_user_raises_404(self):
        owner = UserFactory.create()
        other = UserFactory.create()
        project = ProjectFactory.create(project_admin=owner)
        with self.assertRaises(Http404):
            Project.objects.get_project_by_untrusted_project_id(
                project.id, other)


class PermissionRequestTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.project = ProjectFactory.create(project_admin=self.user)
        self.feature = FeatureFactory.create(app_name='feat')
        self.opt1 = FeatureOptions.objects.create(name="A")
        self.opt2 = FeatureOptions.objects.create(name="B")

    def test_accept_new_permission(self):
        req = PermissionRequest.objects.create(
            requesting_user=self.user, project=self.project,
            requested_feature=self.feature)
        req.feature_options.set([self.opt1])
        req.accept()
        self.assertTrue(req.accepted)
        self.assertIsNotNone(req.responded_on)
        permission = Permission.objects.get(
            project=self.project, feature=self.feature)
        self.assertIn(self.opt1, permission.feature_options.all())
        self.assertEqual(1, len(mail.outbox))

    def test_accept_existing_permission(self):
        permission = Permission.objects.create(
            project=self.project, feature=self.feature)
        permission.feature_options.set([self.opt1])
        req = PermissionRequest.objects.create(
            requesting_user=self.user, project=self.project,
            requested_feature=self.feature)
        req.feature_options.set([self.opt2])
        req.accept()
        permission.refresh_from_db()
        self.assertIn(self.opt2, permission.feature_options.all())
        self.assertIn(self.opt1, permission.feature_options.all())

    def test_accept_auto_approved_no_email(self):
        req = PermissionRequest.objects.create(
            requesting_user=self.user, project=self.project,
            requested_feature=self.feature)
        req.accept(auto_approved=True)
        self.assertEqual(0, len(mail.outbox))

    def test_deny(self):
        req = PermissionRequest.objects.create(
            requesting_user=self.user, project=self.project,
            requested_feature=self.feature)
        req.deny()
        self.assertFalse(req.accepted)
        self.assertIsNotNone(req.responded_on)
        self.assertEqual(1, len(mail.outbox))

    def test_str(self):
        req = PermissionRequest.objects.create(
            requesting_user=self.user, project=self.project,
            requested_feature=self.feature)
        self.assertIn("Permission Request", str(req))

    def test_get_permission_feature_options_for_latest_project(self):
        # Approve the project so it's the user's latest selected
        self.project.ARO_approval = True
        self.project.save()
        self.user.profile.set_last_selected_project(self.project)
        permission = Permission.objects.create(
            project=self.project, feature=self.feature)
        permission.feature_options.set([self.opt1])
        result = list(get_permission_feature_options_for_latest_project(
            self.user, self.feature))
        self.assertEqual([("A", "A")], result)


class PermissionStrTests(TestCase):
    def test_str(self):
        user = UserFactory.create()
        project = ProjectFactory.create(project_admin=user)
        feature = FeatureFactory.create()
        permission = Permission.objects.create(
            project=project, feature=feature)
        self.assertIn("permission for", str(permission))


class ProfileTests(TestCase):
    def test_get_last_selected_when_set(self):
        user = UserFactory.create()
        project = ProjectFactory.create(
            project_admin=user, ARO_approval=True)
        user.profile.set_last_selected_project(project)
        self.assertEqual(project, user.profile.get_last_selected_project())

    def test_get_last_selected_uses_latest_when_unset(self):
        user = UserFactory.create()
        project = ProjectFactory.create(
            project_admin=user, ARO_approval=True)
        # last_selected_project is None
        self.assertEqual(project, user.profile.get_last_selected_project())

    def test_get_last_selected_none_when_no_projects(self):
        user = UserFactory.create()
        self.assertIsNone(user.profile.get_last_selected_project())

    def test_set_last_selected_rejects_unapproved(self):
        user = UserFactory.create()
        project = ProjectFactory.create(
            project_admin=user, ARO_approval=None)
        user.profile.set_last_selected_project(project)
        self.assertIsNone(user.profile.last_selected_project)

    def test_set_last_selected_rejects_other_user(self):
        owner = UserFactory.create()
        other = UserFactory.create()
        project = ProjectFactory.create(
            project_admin=owner, ARO_approval=True)
        other.profile.set_last_selected_project(project)
        self.assertIsNone(other.profile.last_selected_project)

    def test_get_last_selected_falls_back_when_unowned_or_unapproved(self):
        user = UserFactory.create()
        approved = ProjectFactory.create(
            project_admin=user, ARO_approval=True)
        # Force last_selected_project to a project that's not approved
        unapproved = ProjectFactory.create(
            project_admin=user, ARO_approval=None)
        Profile.objects.filter(pk=user.profile.pk).update(
            last_selected_project=unapproved)
        result = user.profile.get_last_selected_project()
        self.assertEqual(approved, result)

    def test_str(self):
        user = UserFactory.create(username="bob@x.com")
        self.assertIn("bob@x.com", str(user.profile))


class AROWhitelistTests(TestCase):
    def test_is_whitelisted_true(self):
        user = UserFactory.create()
        AROWhitelist.objects.create(
            username="abc", permission_granted_by=user)
        result = AROWhitelist.objects.is_username_whitelisted("abc")
        self.assertTrue(result)

    def test_is_whitelisted_false(self):
        self.assertFalse(
            AROWhitelist.objects.is_username_whitelisted("none"))

    def test_add_and_remove(self):
        user = UserFactory.create()
        add_username_to_whitelist(
            username="xx", comment="hi", permission_granted_by=user)
        self.assertTrue(AROWhitelist.objects.filter(username="xx").exists())
        remove_username_from_whitelist("xx")
        self.assertFalse(AROWhitelist.objects.filter(username="xx").exists())

    def test_str(self):
        user = UserFactory.create()
        wl = AROWhitelist.objects.create(
            username="zz", permission_granted_by=user)
        self.assertIn("zz", str(wl))


class Char32UUIDFieldTests(TestCase):
    def test_db_type_is_char_32(self):
        from researcher_workspace.models import Char32UUIDField
        field = Char32UUIDField()
        self.assertEqual("char(32)", field.db_type(connection=None))

    def test_get_db_prep_value_str(self):
        import uuid
        from django.db import connection
        from researcher_workspace.models import Char32UUIDField
        field = Char32UUIDField()
        u = uuid.uuid4()
        result = field.get_db_prep_value(str(u), connection=connection)
        self.assertEqual(u.hex, result)

    def test_get_db_prep_value_none(self):
        from django.db import connection
        from researcher_workspace.models import Char32UUIDField
        field = Char32UUIDField()
        self.assertIsNone(
            field.get_db_prep_value(None, connection=connection))
