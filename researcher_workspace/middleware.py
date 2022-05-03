import base64
import pytz

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.urls import resolve
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


class MetricsAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        current_view = resolve(request.path_info).view_name
        if current_view == 'prometheus-django-metrics':
            # For the metrics /metrics url only
            if request.user.is_superuser:
                return self.get_response(request)

            if 'Authorization' in request.headers:
                auth = request.headers['Authorization']
                if auth.startswith('Basic '):
                    auth = auth.split('Basic ')[1]
                    auth = base64.b64decode(auth).decode('utf-8')
                    username, password = auth.split(':')
                    if (username == settings.METRICS_USERNAME
                            and password == settings.METRICS_PASSWORD):
                        return self.get_response(request)
        else:
            # All other urls
            return self.get_response(request)

        return HttpResponse('Unauthorized', status=401)
