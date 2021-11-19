from datetime import datetime, timedelta, timezone

from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase
from django.core.mail import EmailMessage, EmailMultiAlternatives

from researcher_workspace.utils.freshdesk import FreshdeskEmailBackend

from researcher_workspace.tests.factories import UserFactory


class FreshdeskEmailBackendTests(TestCase):

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

    @patch('researcher_workspace.utils.freshdesk.API')
    def test_init(self, mock_api_class):
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        backend = FreshdeskEmailBackend()
        self.assertEqual(mock_api, backend.api)
        self.assertEqual(settings.FRESHDESK_GROUP_ID, backend.group_id)
        self.assertEqual(settings.FRESHDESK_EMAIL_CONFIG_ID,
                         backend.email_config_id)
        mock_api_class.assert_called_once_with(
            settings.FRESHDESK_DOMAIN, settings.FRESHDESK_KEY)

    @patch('researcher_workspace.utils.freshdesk.API')
    def test_send_emails(self, mock_api_class):
        user = UserFactory.create(email="test@test.test")
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        backend = FreshdeskEmailBackend()

        mail = self._create_mail("here@test.test", user.email,
                                 "subject", "body", backend)
        mail.send()
        mock_api.tickets.create_outbound_email.assert_called_once_with(
            subject='subject', description='body',
            email=[user.email], cc_emails=[], bcc_emails=[],
            email_config_id=settings.FRESHDESK_EMAIL_CONFIG_ID,
            group_id=settings.FRESHDESK_GROUP_ID)

        mock_api.tickets.create_outbound_email.reset_mock()

        mail = self._create_multi_mail("here@test.test", user.email,
                                       "subject", "body", None, backend)
        mail.send()
        mock_api.tickets.create_outbound_email.assert_called_once_with(
            subject='subject', description='body',
            email=[user.email], cc_emails=[], bcc_emails=[],
            email_config_id=settings.FRESHDESK_EMAIL_CONFIG_ID,
            group_id=settings.FRESHDESK_GROUP_ID)

        mock_api.tickets.create_outbound_email.reset_mock()

        mail = self._create_multi_mail("here@test.test", user.email,
                                       "subject", "body", "html_body", backend)
        mail.send()
        mock_api.tickets.create_outbound_email.assert_called_once_with(
            subject='subject', description='html_body',
            email=[user.email], cc_emails=[], bcc_emails=[],
            email_config_id=settings.FRESHDESK_EMAIL_CONFIG_ID,
            group_id=settings.FRESHDESK_GROUP_ID)
