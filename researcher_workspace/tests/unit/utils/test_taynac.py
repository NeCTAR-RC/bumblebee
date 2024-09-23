from unittest.mock import Mock, patch

from django.test import TestCase
from django.core.mail import EmailMessage, EmailMultiAlternatives

from researcher_workspace.utils.taynac import TaynacEmailBackend

from researcher_workspace.tests.factories import UserFactory


class TaynacEmailBackendTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)

    def _create_mail(self, from_email, to_email, subject, message,
                     connection):
        return EmailMessage(
            subject=subject, body=message,
            from_email=from_email, to=[to_email], connection=connection)

    def _create_multi_mail(self, from_email, to_email, subject, message,
                           html_message, connection):
        mail = EmailMultiAlternatives(
            subject=subject, body=message,
            from_email=from_email, to=[to_email], connection=connection)
        if html_message:
            mail.attach_alternative(html_message, 'text/html')
        return mail

    @patch('researcher_workspace.utils.taynac.get_taynac_client')
    def test_init(self, mock_get):
        backend = TaynacEmailBackend()
        mock_get.assert_not_called()
        self.assertIsNone(backend.taynac)

    @patch('researcher_workspace.utils.taynac.get_taynac_client')
    def test_send_emails(self, mock_get):
        user = UserFactory.create(email="test@test.test")
        mock_client = Mock()
        mock_get.return_value = mock_client
        backend = TaynacEmailBackend()
        mail = self._create_mail("here@test.test", user.email,
                                 "subject", "body", backend)
        mail.send()
        mock_get.assert_called_once()
        self.assertEqual(mock_client, backend.taynac)
        mock_client.messages.send.assert_called_once_with(
            subject='subject', body='body',
            recipient=user.email, cc=[], tags=['vds-service'])

        mock_client.messages.send.reset_mock()
        mock_get.reset_mock()

        mail = self._create_multi_mail("here@test.test", user.email,
                                       "subject", "body", None, backend)
        mail.send()
        mock_get.assert_not_called()
        mock_client.messages.send.assert_called_once_with(
            subject='subject', body='body',
            recipient=user.email, cc=[], tags=['vds-service'])

        mock_client.messages.send.reset_mock()

        mail = self._create_multi_mail("here@test.test", user.email,
                                       "subject", "body", "html_body", backend)
        mail.send()
        mock_client.messages.send.assert_called_once_with(
            subject='subject', body='html_body',
            recipient=user.email, cc=[], tags=['vds-service'])
