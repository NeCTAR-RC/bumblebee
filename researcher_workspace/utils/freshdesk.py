from django.conf import settings

from freshdesk.v2.api import API


def get_api():
    return API(settings.FRESHDESK_DOMAIN, settings.FRESHDESK_KEY)


def create_ticket(**kwargs):
    api = get_api()
    return api.tickets.create_ticket(**kwargs)
