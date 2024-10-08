from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase

from researcher_workspace.utils.freshdesk import get_api, create_ticket


class FreshdeskTicketTests(TestCase):
    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)

    @patch('researcher_workspace.utils.freshdesk.API')
    def test_get_api(self, mock_api_class):
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        api = get_api()
        self.assertEqual(mock_api, api)
        mock_api_class.assert_called_once_with(settings.FRESHDESK_DOMAIN,
                                               settings.FRESHDESK_KEY)

    @patch('researcher_workspace.utils.freshdesk.API')
    def test_create_ticket(self, mock_api_class):
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.tickets.create_ticket.return_value = 1234
        ticket = create_ticket(a=1, b=2)
        self.assertEqual(1234, ticket)
        mock_api_class.assert_called_once()
        mock_api.tickets.create_ticket.assert_called_once_with(a=1, b=2)
