from django import template

register = template.Library()


@register.filter(name='get_class')
def get_class(obj):
    return obj.__class__.__name__


@register.filter(name="get_dir")
def get_dir(obj):
    return dir(obj)


@register.filter(name="get_attr")
def get_attr(obj, attr):
    return obj.__getattribute__(attr)
