from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from researcher_desktop.tests.factories import DesktopTypeFactory
from researcher_workspace.tests.factories import FeatureFactory


@patch('vm_manager.management.commands.cronjob.desktops_feature')
class CronjobTests(TestCase):

    def setUp(self):
        self.feature = FeatureFactory.create(app_name='feature')
        self.desktop_type = DesktopTypeFactory.create(
            id='desktop', name='desktop', feature=self.feature)

    def _make_run_mock(self):
        return {'expired': 0, 'warned': 0}

    @patch('vm_manager.management.commands.cronjob.InstanceExpirer')
    def test_shelve_job(self, mock_expirer, mock_feature):
        mock_feature.return_value = self.feature
        mock_expirer.return_value.run.return_value = self._make_run_mock()
        out = StringIO()
        call_command('cronjob', '--shelve', stdout=out)
        mock_expirer.assert_called_once_with(dry_run=False, verbose=False)
        mock_expirer.return_value.run.assert_called_once_with(self.feature)

    @patch('vm_manager.management.commands.cronjob.ResizeExpirer')
    def test_downsize_job(self, mock_expirer, mock_feature):
        mock_feature.return_value = self.feature
        mock_expirer.return_value.run.return_value = self._make_run_mock()
        out = StringIO()
        call_command('cronjob', '--downsize', stdout=out)
        mock_expirer.assert_called_once_with(dry_run=False, verbose=False)
        mock_expirer.return_value.run.assert_called_once_with(self.feature)

    @patch('vm_manager.management.commands.cronjob.VolumeExpirer')
    def test_archive_job(self, mock_expirer, mock_feature):
        mock_feature.return_value = self.feature
        mock_expirer.return_value.run.return_value = self._make_run_mock()
        out = StringIO()
        call_command('cronjob', '--archive', stdout=out)
        mock_expirer.assert_called_once_with(dry_run=False, verbose=False)
        mock_expirer.return_value.run.assert_called_once_with(self.feature)

    @patch('vm_manager.management.commands.cronjob.ArchiveExpirer')
    def test_delete_archives_job(self, mock_expirer, mock_feature):
        mock_feature.return_value = self.feature
        mock_expirer.return_value.run.return_value = self._make_run_mock()
        out = StringIO()
        call_command('cronjob', '--delete-archives', stdout=out)
        mock_expirer.assert_called_once_with(dry_run=False, verbose=False)
        mock_expirer.return_value.run.assert_called_once_with(self.feature)

    @patch('vm_manager.management.commands.cronjob.InstanceExpirer')
    def test_dry_run_and_verbose(self, mock_expirer, mock_feature):
        mock_feature.return_value = self.feature
        mock_expirer.return_value.run.return_value = self._make_run_mock()
        with patch('builtins.print') as mock_print:
            call_command('cronjob', '--shelve', '--dry-run', '--verbose')
        mock_expirer.assert_called_once_with(dry_run=True, verbose=True)
        printed = " ".join(c.args[0] for c in mock_print.call_args_list)
        self.assertIn("--dry-run", printed)

    def test_no_args_does_nothing(self, mock_feature):
        out = StringIO()
        call_command('cronjob', stdout=out)
        mock_feature.assert_not_called()
