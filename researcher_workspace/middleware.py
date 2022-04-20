import pytz

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tzname = None
        try:
            if hasattr(request.user, 'profile'):
                tzname = request.user.profile.timezone
        except ObjectDoesNotExist:
            pass
        if tzname:
            timezone.activate(pytz.timezone(tzname))
        else:
            timezone.deactivate()
        return self.get_response(request)
