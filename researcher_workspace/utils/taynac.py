from django.core.mail.backends.base import BaseEmailBackend

from vm_manager.utils import utils


TAGS = ['vds-service']


def get_taynac_client():
    return utils.get_nectar().taynac


class TaynacEmailBackend(BaseEmailBackend):

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.taynac = None

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        if not self.taynac:
            self.taynac = get_taynac_client()

        num_sent = 0
        for message in email_messages:
            sent = self._send(message)
            if sent:
                num_sent += 1
        return num_sent

    def _send(self, message):
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
            # to be a str, so we just take the first 'to' address as the
            # primary recipient only and the other 'to' addresses become 'cc's.
            self.taynac.messages.send(
                subject=message.subject,
                body=body,
                recipient=recipients.pop(0),
                cc=recipients,
                tags=TAGS)
        except Exception:
            if not self.fail_silently:
                raise
            return False
        return True
