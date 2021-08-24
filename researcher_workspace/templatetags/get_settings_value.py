from django import template
from researcher_workspace import settings

register = template.Library()


@register.filter(name='get_settings_value')
def get_settings_value(name):
    return getattr(settings, name, "")
