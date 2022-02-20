from django.template import loader
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.conf import settings

from researcher_workspace.templatetags.group_filters import has_group


def redirect_home(request):
    return HttpResponseRedirect(reverse('home', args=request))


def not_support_staff(user):
    return not has_group(user, 'Support Staff')


def agreed_to_terms(user):
    # The alternative to this is a lazy import of 'User' and
    # an 'isinstance' test.  We can't do a regular import because it raises
    # django.core.exceptions.AppRegistryNotReady: Apps aren't loaded yet.
    return getattr(user, 'terms_version', 0) >= settings.TERMS_VERSION


def offset_month_and_year(month_offset, month, year):
    offset_month = month - month_offset
    return offset_month % 12 + 1, year + (offset_month // 12)


def send_notification(user, template_name, context):
    ''' Format and send an email notification to the user.  The template
    should render as a string that consists of the subject text followed by
    a blank line and then multiple lines comprising an HTML message body.
    '''

    text = format_notification(user, template_name, context)
    subject, _, body = text.partition('\n\n')
    user.email_user(subject.strip(), body.strip())


def format_notification(user, template_name, context):
    context['user'] = user
    return loader.render_to_string(template_name, context)
