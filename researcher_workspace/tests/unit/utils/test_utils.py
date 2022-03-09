from unittest.mock import Mock

from django.test import TestCase


from researcher_workspace.utils import send_notification


class UtilsTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)

    def test_send_notification(self):
        mock_user = Mock()
        mock_user.get_full_name = 'Fred'
        send_notification(mock_user, 'email/test.html',
                          {'location': 'Pleasure Dome'})
        mock_user.email_user.assert_called_once_with(
            'Welcome to the Bumblebee service.',
            'Hi Fred,\n<br>\n<br>\nWelcome to the Pleasure Dome')
