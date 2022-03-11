from django.test import TestCase

from vm_manager.management.commands.cronjob import Command


class CronjobTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)

    def test_instantiate(self):
        # Just make sure there are no compilation errors ... for now
        command = Command()
