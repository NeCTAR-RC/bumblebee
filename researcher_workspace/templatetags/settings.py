from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def get_setting(name):
    '''Return the value of a setting from Django's conf.settings.
    '''

    return getattr(settings, name, '')


@register.simple_tag(takes_context=True)
def add_setting(context, setting_name, context_name):
    '''Add the value of a setting from Django's conf.settings to
    the template context.  Returns an empty string.
    '''

    context[context_name] = getattr(settings, setting_name, '')
    return ''
