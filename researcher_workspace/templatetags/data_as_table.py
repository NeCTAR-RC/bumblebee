import collections
from django import template
from django.template.defaultfilters import safe

import six

register = template.Library()


def iterable(arg):
    return (
        isinstance(arg, collections.Iterable)
        and not isinstance(arg, six.string_types)
    )


@register.filter(name='print_data_as_html_table')
def print_data_as_html_table(data) -> str:
    table = '<table>'
    if hasattr(data, 'items'):
        for key, value in data.items():
            if iterable(value):
                value = print_data_as_html_table(value)
            table += f"<tr><td>{key}</td><td>{value}</td></tr>"
    else:
        for value in data:
            if iterable(value):
                value = print_data_as_html_table(value)
            table += f"<tr><td>{value}</td></tr>"
    return safe(table + '</table>')


@register.filter(name='print_2d_list_in_table_body')
def print_2d_list_in_table_body(data) -> str:
    table = '<tbody>'
    for item in data:
        table += "<tr>"
        for value in item:
            if iterable(value):
                value = print_data_as_html_table(value)
            table += f"<td>{value}</td>"
        table += "</tr>"
    return safe(table + '</tbody>')
