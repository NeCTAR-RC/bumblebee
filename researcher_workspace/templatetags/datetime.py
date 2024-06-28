from datetime import datetime, timedelta

from django import template
from django.utils import timezone

register = template.Library()


@register.simple_tag
def time_of_day():
    cur_time = datetime.now(tz=timezone.get_current_timezone())
    if cur_time.hour < 12:
        return 'Morning'
    elif 12 <= cur_time.hour < 18:
        return 'Afternoon'
    else:
        return 'Evening'


@register.simple_tag
def period(delta: timedelta):
    """Renders a timedelta as days, hours and minutes.

    :param delta: The timedelta to render.
    """

    total = delta.total_seconds()
    days = int(total // (60 * 60 * 24))
    total = int(total % (60 * 60 * 24))
    hours = int(total // (60 * 60))
    total = int(total % (60 * 60))
    minutes = int(total / 60)

    if days:
        if hours:
            if minutes:
                return f"{days} days, {hours} hours and {minutes} minutes"
            else:
                return f"{days} days and {hours} hours"
        else:
            if minutes:
                return f"{days} days and {minutes} minutes"
            else:
                return f"{days} days"
    else:
        if hours:
            if minutes:
                return f"{hours} hours and {minutes} minutes"
            else:
                return f"{hours} hours"
        else:
            return f"{minutes} minutes"
