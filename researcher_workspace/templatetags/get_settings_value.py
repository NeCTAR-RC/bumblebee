from django import template
from django.conf import settings

register = template.Library()


@register.filter(name='get_settings_value')
def get_settings_value(name):
    return getattr(settings, name, "")
