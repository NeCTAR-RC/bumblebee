from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings


from freshdesk.v2.api import API


class FreshdeskEmailBackend(BaseEmailBackend):

    def __init__(self):
        super().__init__()
        self.api = API(settings.FRESHDESK_DOMAIN, settings.FRESHDESK_KEY)
        self.email_config_id = settings.FRESHDESK_EMAIL_CONFIG_ID
        self.group_id = settings.FRESHDESK_GROUP_ID

    def send_messages(self, email_messages):
        for message in email_messages:
            # A message could be an EmailMessage or an EmailMultiAlternatives
            # For the latter case, we want to use the alternative with
            # mimetype 'text/html' (if present) for the Freshdesk ticket.
            # (The 'next(comprehension, None)' pattern gives the first
            # matching element or None.
            html_body = next(
                (alt[0] for alt in getattr(message, 'alternatives', [])
                 if alt[1] == "text/html"),
                None)
            body = html_body or message.body

            self.api.tickets.create_outbound_email(
                subject=message.subject,
                description=body,
                email=message.to,
                cc_emails=message.cc,
                bcc_emails=message.bcc,
                email_config_id=self.email_config_id,
                group_id=self.group_id)
