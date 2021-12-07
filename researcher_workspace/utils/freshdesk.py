from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings

from freshdesk.v2.api import API


class FreshdeskEmailBackend(BaseEmailBackend):

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)

        self.domain = settings.FRESHDESK_DOMAIN
        self.key = settings.FRESHDESK_KEY
        self.email_config_id = int(settings.FRESHDESK_EMAIL_CONFIG_ID)
        self.group_id = int(settings.FRESHDESK_GROUP_ID)
        self.api = None

    def send_messages(self, email_messages):
        """
        Send one or more EmailMessage objects and return the number of email
        messages sent.
        """
        if not email_messages:
            return 0

        if not self.api:
            self.api = API(self.domain, self.key)

        num_sent = 0
        for message in email_messages:
            sent = self._send(message)
            if sent:
                num_sent += 1
        return num_sent

    def _send(self, message):
        """A helper method that does the actual sending."""
        if not message.recipients():
            return False

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
        recipients = message.recipients()

        try:
            # Django requires to/cc to be lists, but FD requires the 'to' addr
            # to be a str, so we just take the first only and the others
            # become CC recipients
            self.api.tickets.create_outbound_email(
                subject=message.subject,
                description=body,
                email=recipients.pop(0),
                cc_emails=recipients,
                email_config_id=self.email_config_id,
                group_id=self.group_id)
        except Exception:
            if not self.fail_silently:
                raise
            return False
        return True
