from django.conf import settings
from django.core import mail
from django.test import TestCase

from researcher_workspace.tests.factories import UserFactory, \
    ProjectFactory


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
