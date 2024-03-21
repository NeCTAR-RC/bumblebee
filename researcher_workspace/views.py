import csv
from datetime import datetime
from dateutil.relativedelta import relativedelta
from io import BytesIO
import logging

import pandas
import pytz

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import user_logged_in, user_logged_out
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.core.mail import mail_managers
from django.dispatch import receiver
from django.http import HttpResponse, HttpResponseRedirect, Http404, StreamingHttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.timezone import utc
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from researcher_desktop.utils.utils import get_desktop_type, get_applicable_zones

from .constants import USAGE
from .forms import UserSearchForm, ProjectForm, \
    ProfileForm, PermissionRequestForm, SupportRequestForm
from .models import PermissionRequest, Feature, Project, AROWhitelist, \
    add_username_to_whitelist, remove_username_from_whitelist, User
from .templatetags.group_filters import has_group
from .utils import redirect_home, agreed_to_terms, not_support_staff, \
    offset_month_and_year
from .utils import send_notification
from .utils.faculty_mapping import FACULTIES, FACULTY_MAPPING
from .utils.freshdesk import create_ticket

import researcher_desktop.views as rdesk_views

from vm_manager.constants import NO_VM
from vm_manager.utils.utils import get_nectar
from vm_manager.views import desktop_limit_check

logger = logging.getLogger(__name__)


def _get_users_for_report():
    # backend = ResplatLDAPBackend()
    django_users = User.objects.filter(is_active=True).order_by('date_joined')
    users = []
    num = 1
    for django_user in django_users:
        user = {'id': django_user.id, 'name': django_user.get_full_name(), 'username': django_user.username,
                'email': django_user.email, 'date_joined': django_user.date_joined, 'num': num}
        # ldap_user = backend.get_user(django_user.id).ldap_user.attrs
        # if ldap_user:
        #     user['department'] = ldap_user['department']
        #     user['person_type'] = ldap_user['auedupersontype'][0]
        # else:
        user['department'] = [""]
        user['person_type'] = ""
        users.append(user)
        num += 1
    return users


@login_required(login_url='login')
def user_search(request):
    if not (request.user.is_staff or has_group(request.user, 'Support Staff')):
        return custom_page_not_found(request)

    # Download csv of all users on the site
    if request.method == 'POST':
        users = _get_users_for_report()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="Orion_User_Report.csv"'
        writer = csv.writer(response)
        columns = [key for key in users[0].keys()]
        writer.writerow(columns)
        for user in users:
            writer.writerow([user[key] for key in columns])
        return response

    # Search for users
    if request.GET:
        form = UserSearchForm(request.GET)
        users = []
        # if form.is_valid():
        #    search = {k: v for k, v in form.cleaned_data.items() if v}
        #    # LDAP search
        #    if search:
        #        users = LDAP().list(**search)
        #        # For mail searches, also attempt to search for UID based on alias
        #        if 'mail' in search and 'uid' not in search:
        #            extra_results = LDAP().list(uid=search['mail'].split('@')[0])
        #            users += [u for u in extra_results if u not in users]
        return render(request, 'researcher_workspace/staff/user_search.html', {'users': users, 'form': form})

    # Show user reporting page
    form = UserSearchForm()
    users = _get_users_for_report()
    return render(request, 'researcher_workspace/staff/user_reporting.html', {'users': users, 'form': form,
                  'first_date': users[0]['date_joined'], 'last_date': users[-1]['date_joined']})


@login_required(login_url='login')
def user_search_details(request, username):
    if not (request.user.is_staff or has_group(request.user, 'Support Staff')):
        return custom_page_not_found(request)
    if request.method == 'POST':
        add_or_delete = request.POST.get('add_or_delete', 'add')
        comment = request.POST.get('aro_whitelist_comment')
        if add_or_delete == 'add':
            add_username_to_whitelist(username=username, comment=comment, permission_granted_by=request.user)
        elif add_or_delete == 'delete':
            remove_username_from_whitelist(username=username)
    try:
        is_user = User.objects.get(username=username).id
    except User.DoesNotExist:
        is_user = False
    aro_whitelisted = AROWhitelist.objects.is_username_whitelisted(username)
    # ldap = LDAP()
    # try:
    #    user = ldap.get(uid=username)
    # except LDAPDoesNotExist:
    return render(request, 'researcher_workspace/staff/user_search_details.html', {'user_does_not_exist': True,
                  'is_user': is_user, 'aro_whitelisted': aro_whitelisted, 'user_details': {'uid': username}})
#    try:
#        api_return = call_boomi.api_call(username=username)
#        is_student = api_return.pop('is_student_api')
#        api_user = api_return if not is_student else api_return['student'][0]
#    except requests.exceptions.HTTPError:
#        api_user = {}
#    if 'supervisor_staff_id' in api_user:
#        supervisor_staff_id = api_user.pop('supervisor_staff_id').strip()
#        if supervisor_staff_id:
#            try:
#                supervisor_username = call_boomi.api_call(uom_id=supervisor_staff_id).pop('user_name')
#                api_user['supervisor'] = f"<a href='{ reverse('user_search_details', args=[supervisor_username]) }?{ request.GET.urlencode() }'>{ supervisor_username }</a>"
#            except requests.exceptions.HTTPError:
#                api_user['supervisor'] = f"BOOMI error in looking up the supervisor. Supervisor's id is: {supervisor_staff_id}"
#
#    try:
#        if len(api_user['enrolment']['Supervisors']['Supervisor']) > 0:
#            for supervisor in api_user['enrolment']['Supervisors']['Supervisor']:
#                supervisor_staff_id = supervisor.pop('supervisor_staff_id').strip()
#                try:
#                    supervisor_details = call_boomi.api_call(uom_id=supervisor_staff_id)
#                    supervisor_username = supervisor_details['user_name'] if not supervisor_details['is_student_api'] else supervisor_details['student'][0]['username']
#                    supervisor['supervisor'] = f"<a href='{reverse('user_search_details', args=[supervisor_username])}?{request.GET.urlencode()}'>{supervisor_username}</a>"
#                except requests.exceptions.HTTPError:
#                    api_user['supervisor'] = f"BOOMI error in looking up the supervisor. Supervisor's id is: {supervisor_staff_id}"
#    except KeyError:
#        pass
#
#    return render(request, 'researcher_workspace/staff/user_search_details.html',
#                  {'user_details': user, 'user_fields': LDAP.fields, 'api_user': api_user,
#                   'is_user': is_user, 'aro_whitelisted': aro_whitelisted})
#


@login_required(login_url='login')
def orion_report(request):
    if not (request.user.is_staff or has_group(request.user, 'Support Staff')):
        return custom_page_not_found(request)
    if request.method != 'POST':
        return render(request,
                      'researcher_workspace/staff/orion_reporting.html',
                      rdesk_views.rd_report_page())
    reporting_months = int(request.POST.get("reporting_months", "6"))
    if reporting_months < 1:
        raise ValueError(f"{request.user} requested Orion reporting for reporting_months < 1")
    output = BytesIO()
    writer = pandas.ExcelWriter(output, engine='xlsxwriter')
    vm_report = rdesk_views.rd_report(reporting_months)
    users = _get_users_for_report()
    now = datetime.now(utc)
    user_count = dict([(offset_month_and_year(month_offset, now.month, now.year), FACULTIES.copy())
                       for month_offset in range(reporting_months, 0, -1)])
    for user in users:
        user["simple_date"] = (user["date_joined"].month, user["date_joined"].year)
    for date in user_count:
        for user in [user for user in users
                     if user["simple_date"][1] < date[1]
                     or (user["simple_date"][1] == date[1]
                         and user["simple_date"][0] <= date[0])]:
            try:
                user_count[date][FACULTY_MAPPING[user["department"][0]]] += 1
            except KeyError:
                user_count[date]['NOT_MAPPED'] += 1
            user_count[date]['Total'] += 1

    user_count_report = [
        [f"01/{month[0]}/{month[1]}"] + [user_count[month][faculty] for faculty in FACULTIES.keys()]
        for month in user_count.keys()]
    user_count_report_data_frame = pandas.DataFrame(user_count_report, columns=['Month'] + list(FACULTIES.keys()))
    user_count_report_data_frame.to_excel(writer, sheet_name="User growth")
    for report in vm_report:
        report_data_frame = pandas.DataFrame(
            [[f"01/{month[0]}/{month[1]}"] + [value[1][month] for value in report["values"]]
             for month in report["values"][0][1].keys()],
            columns=['Month'] + [operating_system for operating_system, values in report["values"]])
        report_data_frame.to_excel(writer, sheet_name=report["name"])

    # Project Usage Count
    n = get_nectar()
    if not settings.OS_PROJECT_ID:
        logger.info("No usage info available: project id not configured")
    else:
        usage_count = dict(
            [(offset_month_and_year(month_offset, now.month, now.year),
              USAGE.copy())
             for month_offset in range(reporting_months, 0, -1)])
        for date in usage_count:
            start_date = datetime(day=1, month=date[0], year=date[1])
            end_date = start_date + relativedelta(months=+1)
            usage = n.nova.usage.get(settings.OS_PROJECT_ID,
                                     start_date, end_date)
            usage_count[date]['CPU Hours'] = round(usage.total_vcpus_usage, 2)
            usage_count[date]['Disk GB-Hours'] = round(usage.total_local_gb_usage, 2)
            usage_count[date]['RAM MB-Hours'] = round(usage.total_memory_mb_usage, 2)
            usage_count[date]['Servers Activity'] = len(usage.server_usages)

            usage_report = [
                [f"01/{month[0]}/{month[1]}"] + [usage_count[month][usage]
                                                 for usage in USAGE.keys()]
                for month in usage_count.keys()]
            usage_report_data_frame = pandas.DataFrame(
                usage_report, columns=['Month'] + list(USAGE.keys()))
            usage_report_data_frame.to_excel(writer,
                                             sheet_name="Project Usage")

    writer.save()
    output.seek(0)
    response = StreamingHttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=Orion_Report.xlsx'
    return response


def index(request):
    if request.user.is_authenticated:
        return redirect_home(request)
    else:
        return render(request, 'researcher_workspace/index.html')


@receiver(user_logged_in)
def on_login(sender, user, request, **kwargs):
    """
    The handler for the user_logged_in signal
    """
    if (getattr(request, 'user', None)
            and hasattr(request.user, 'get_full_name')):
        logger.info('User %s has logged in', request.user.get_full_name())
        messages.info(request, format_html(
            f'Welcome <strong>{request.user.first_name}</strong>'))


def logout(request):
    auth_logout(request)
    return render(request, 'researcher_workspace/index.html')


@receiver(user_logged_out)
def on_logout(sender, user, request, **kwargs):
    """
    The handler for the user_logged_out signal
    """
    if (getattr(request, 'user', None)
            and hasattr(request.user, 'get_full_name')):
        messages.info(request, format_html(
            f'Goodbye <strong>{request.user.first_name}</strong>'))
        logger.info('User %s has logged out', request.user.get_full_name())


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
@user_passes_test(test_func=not_support_staff, login_url='staff_home',
                  redirect_field_name=None)
def home(request):
    # Handle edge cases
    if (hasattr(settings, 'GENERAL_WARNING_MESSAGE')
            and bool(settings.GENERAL_WARNING_MESSAGE)):
        messages.warning(
            request, format_html(settings.GENERAL_WARNING_MESSAGE))

    # Get user's Project(s)
    project_id = request.POST.get('project', None)
    current_projects = Project.objects.filter(project_admin=request.user).exclude(ARO_approval=False).order_by('-created')
    if project_id:
        selected_project = Project.objects.get_project_by_untrusted_project_id(project_id, request.user)
        if selected_project.ARO_approval:
            request.user.profile.set_last_selected_project(selected_project)
        else:
            selected_project = request.user.profile.get_last_selected_project()
    else:
        selected_project = request.user.profile.get_last_selected_project()

    if selected_project:
        selected_project_features = selected_project.permissions.all()
    else:
        selected_project_features = []

    # Render the features to display on the user's Do tab
    active_module = None
    modules = []
    scripts = []
    for feature in selected_project_features:
        feature_conf = apps.app_configs.get(feature.app_name)
        if not feature_conf:
            # User has been enabled for a feature that is not implemented
            continue
        feature_application = feature_conf.module
        feature_modules = feature_application.views.render_modules(request)

        for module, alt_module, script, state in feature_modules:
            if state == NO_VM:
                modules.append(module)
            else:
                modules.append(alt_module)
                active_module = module
            scripts.append(script)

#    # Render the features to display on the Discover tab
#    discover_features = []
#    # Get the features the user has already requested for this project
#    requested_features = [request.requested_feature for request in PermissionRequest.objects.filter(project=selected_project, accepted=None)]
#    # Render all the features
#    for feature in Feature.objects.filter(feature_or_service=True):
#        # Create the variables necessary for rendering
#        previously_requested = feature in requested_features
#        project_already_has_feature = feature in selected_project_features
#        # If the feature is available, create the form for requesting it
#        if feature.currently_available:
#            try:
#                permission_feature_options = Permission.objects.get(project=selected_project, feature=feature).feature_options.all()
#            except Permission.DoesNotExist:
#                permission_feature_options = FeatureOptions.objects.none()
#            # The options you can request are the options on the feature, minus the options you already have access to
#            # request_form_options = [(option.id, option.name) for option in feature.options.difference(permission_feature_options)]
#            request_form_options = [(option.id, option.name) for option in permission_feature_options]
#            request_form = PermissionRequestForm(choices=request_form_options) if request_form_options else ""
#            if request_form:
#                try:
#                    # If you've already requested access, then pre-tick the options you requested
#                    requested_feature_options = PermissionRequest.objects.get(project=selected_project, requested_feature=feature, accepted=None).feature_options.values_list('id', flat=True)
#                    request_form.fields["feature_options"].initial = list(requested_feature_options)
#                except PermissionRequest.DoesNotExist:
#                    pass
#        else:
#            request_form = ""
#        # User can request access if there's a valid request form, or if the feature has not been granted access and there is not an already active request
#        requestable = request_form or (not project_already_has_feature and not previously_requested)
#        feature_html = loader.render_to_string('researcher_workspace/home/discover/feature.html',
#            {'feature': feature, 'previously_requested': previously_requested,
#             'project_already_has_feature': project_already_has_feature,
#             'request_form': request_form, 'requestable': requestable}, request)
#        discover_features.append(feature_html)
#
    # Get the services to display on the Discover tab
    # discover_services = [loader.render_to_string('researcher_workspace/home/discover/service.html',
    #        {'service': service}, request) for service in Feature.objects.filter(feature_or_service=False)]
    context = {
        'active_module': active_module,
        'modules': modules,
        'scripts': scripts,
        'projects': current_projects,
        'selected_project': selected_project,
        # 'discover_features': discover_features,  # unused
        # 'discover_services': discover_services   # unused
    }

    # Render
    return render(request, 'researcher_workspace/home/home.html', context)


# def login(request):
#     return render(request, 'registration/login.html')


def about(request):
    return render(request, 'researcher_workspace/about.html')


@ensure_csrf_cookie
def terms(request):
    show_agree = (request.user
                  and isinstance(request.user, User)
                  and request.user.terms_version < settings.TERMS_VERSION)
    return render(request, 'researcher_workspace/terms.html',
                  {'show_agree': show_agree,
                   'version': settings.TERMS_VERSION})


def agree_terms(request, version):
    if (request.method == 'POST' and request.user
            and isinstance(request.user, User)):
        if (version == settings.TERMS_VERSION
                and version > request.user.terms_version):
            if request.user.terms_version == 0:
                # If this is the first time they have agreed to the T&C's
                # send the "Welcome" email to the user
                context = {'user': request.user}
                send_notification(request.user, 'email/welcome.html', context)
            request.user.terms_version = version
            request.user.date_agreed_terms = datetime.now(utc)
            request.user.save()
        return HttpResponse(status=200)
    else:
        return HttpResponse(status=400)


@login_required(login_url='login')
@csrf_exempt
def help(request):
    # Force the upload form to use the Temp file upload handler (not memory)
    # so we can read the temp file from disk
    request.upload_handlers = [TemporaryFileUploadHandler(request)]
    initial = {'email': request.user.email}
    form = SupportRequestForm(initial=initial)

    if request.method == 'POST':
        form = SupportRequestForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Massage subject into one line or provide a default subject
                subject = form.cleaned_data['subject'].strip()
                if subject:
                    subject = '; '.join(subject.splitlines())
                else:
                    subject = "Virtual Desktop support request"
                # Convert linebreaks in the message to HTML <br> tags.
                body = '<br/>'.join(form.cleaned_data['message'].splitlines())
                ticket_payload = {
                    'name': request.user.get_full_name(),
                    'email': request.user.email,
                    'subject': subject,
                    'description': body,
                    'tags': ['Virtual Desktop'],
                }

                # Handle uploaded file
                screenshot = request.FILES.get('screenshot')
                if screenshot:
                    ticket_payload['attachments'] = [
                        screenshot.temporary_file_path()]

                ticket = create_ticket(**ticket_payload)
                if ticket:
                    messages.success(
                        request,
                        'Your support request has been submitted!')
                    return HttpResponseRedirect(reverse('help'))
                else:
                    raise Exception('Freshdesk ticket creation failed.')

            except Exception:
                messages.error(
                    request,
                    'There was an error submitting your support request. '
                    'Please submit the request as an email.')
                logger.exception('Error submitting ticket')

    return render(request, 'researcher_workspace/help.html', {'form': form})


def custom_page_not_found(request, exception=None):
    logger.warning(f'Page not found: {request.path}')
    return render(request, 'researcher_workspace/404.html')


def custom_page_error(request, exception=None):
    message = 'Something went wrong'
    if exception:
        logger.exception(message, exception)
    else:
        user = getattr(request, 'user', None)
        logger.error(f"{message} user={user} path={request.path}")
    return render(request, 'researcher_workspace/500.html')


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def desktop_details(request, desktop_name):
    desktop_type = get_desktop_type(desktop_name)
    zones = get_applicable_zones(desktop_type)
    launch_blocked = desktop_limit_check(request.user, desktop_type)
    return render(request, 'researcher_workspace/desktop_details.html',
                  {'app_name': 'researcher_workspace',
                   'launch_allowed': not launch_blocked,
                   'desktop_type': desktop_type,
                   'applicable_zones': zones})


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def request_feature_access(request, feature_app_name):
    if request.method == 'POST':
        feature = Feature.objects.get_feature_by_untrusted_feature_name(feature_app_name, request.user)
        request_form_options = [(option.id, option.name) for option in feature.options.all()]
        form = PermissionRequestForm(request.POST, choices=request_form_options)
        if form.is_valid() or not request_form_options:
            if request_form_options:
                feature_options = form.cleaned_data['feature_options']
            else:
                feature_options = []
            current_project = request.user.profile.get_last_selected_project()
            previous_permission_request = PermissionRequest.objects.filter(project=current_project, requested_feature=feature, accepted=None).first()
            if not previous_permission_request:
                permission_request = PermissionRequest(requesting_user=request.user,
                                   project=current_project, requested_feature=feature)
                permission_request.save()
                permission_request.feature_options.set(feature_options)
                if feature.auto_approved:
                    permission_request.accept()
            else:
                previous_permission_request.feature_options.set(feature_options)
                previous_permission_request.save()
    return HttpResponseRedirect(reverse('home') + '#Discover')


def _notify_managers_to_review_project(project, action):
    mail_managers("Project Request",
                  f"{project.project_admin.username} has {action} \"{project.title}\".\n"
                  f"ARO - {project.ARO} \n"
                  f"Project Description - {project.description} \n"
                  f"Kindly review the project here {settings.SITE_URL}"
                  f"{reverse('admin:researcher_workspace_project_change', args=(project.id,))}")


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def new_project(request):
    limit = settings.LIMIT_WORKSPACES_PER_USER
    if limit:
        if Project.objects.filter(project_admin=request.user).count() >= limit:
            return render(request,
                          'researcher_workspace/project/no_more_projects.html',
                          {'limit': limit})

    if request.method == 'POST':
        my_project = Project(project_admin=request.user)
        form = ProjectForm(request.POST, instance=my_project)
        if form.is_valid():
            form.save()
            if settings.AUTO_APPROVE_WORKSPACES:
                my_project.accept(auto_approved=True)
                messages.success(request, format_html(
                    f'Your workspace <strong>{my_project.title}</strong> '
                    'has been created and auto-approved.'))
            else:
                _notify_managers_to_review_project(my_project, "created")
                messages.success(request, format_html(
                    f'Your workspace <strong>{my_project.title}</strong> '
                    'has been created. '
                    'You may start using it once it has been approved.'))
            return HttpResponseRedirect(reverse('home'))
    else:
        form = ProjectForm()
    required_fields = [field_name for field_name, field in form.fields.items()
                       if field.required]
    return render(request, 'researcher_workspace/project/project_new.html',
                  {'form': form, 'required_fields': required_fields})


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def projects(request):
    limit = getattr(settings, 'LIMIT_WORKSPACES_PER_USER', 0)
    user_projects = Project.objects.filter(project_admin=request.user) \
                                   .order_by('-created')
    allow_new_project = limit == 0 or limit < user_projects.count()
    return render(request,
                  'researcher_workspace/project/project_list.html',
                  {'user_projects': user_projects,
                   'allow_new_project': allow_new_project})


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def project_edit(request, project_id):
    if request.method == 'POST':
        project = Project.objects.get_project_by_untrusted_project_id(
            project_id, request.user)
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            if project.ARO_approval is None:
                _notify_managers_to_review_project(project, "updated")
            messages.success(request, format_html(
                f'Your project <strong>{project.title}</strong> '
                'has been edited successfully.'))
            return HttpResponseRedirect(reverse('home'))
    else:
        project = Project.objects.get_project_by_untrusted_project_id(
            project_id, request.user)
        form = ProjectForm(instance=project)
    required_fields = [field_name for field_name, field
                       in form.fields.items() if field.required]
    return render(request, 'researcher_workspace/project/project_edit.html',
                  {'form': form, 'required_fields': required_fields})


@login_required(login_url='login')
def profile(request):
    profile = request.user.profile
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, format_html(
                'Your profile has been updated.'))
            return HttpResponseRedirect(reverse('home'))
    else:
        form = ProfileForm(instance=profile)
    return render(request, 'researcher_workspace/profile.html',
                  {'form': form, 'timezones': pytz.common_timezones, })


@login_required(login_url='login')
def staff_home(request):
    if not_support_staff(request.user):
        raise Http404()
    form = UserSearchForm()
    return render(request, 'researcher_workspace/staff/staff_home.html', {'form': form})


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def report(request):
    return render(request, 'researcher_workspace/report.html', rdesk_views.rd_report_for_user(request.user))


@login_required(login_url='login')
@user_passes_test(test_func=agreed_to_terms, login_url='terms',
                  redirect_field_name=None)
def learn(request):
    return render(request, 'researcher_workspace/learn.html')


def login_fail(request):
    return render(request, 'researcher_workspace/login_fail.html')


def healthcheck(request):
    return HttpResponse('OK')
