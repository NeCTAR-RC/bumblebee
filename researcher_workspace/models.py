from datetime import datetime, timezone
import logging
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.http import Http404

from researcher_workspace.utils.FoR_codes import FOR_CODE_CHOICES
from researcher_workspace.utils import send_notification


logger = logging.getLogger(__name__)

utc = timezone.utc


class Char32UUIDField(models.UUIDField):
    """A UUIDField variant that use char(32) to hold the UUID.

    This is a compatibility hack for MySQL / MariaDB.  Prior to
    MariaDB 10.7, Django uses a char(32) column to hold UUIDs.
    In 10.7+, there is a native uuid column type.  In Django 5,
    the UUIDField class uses the uuid column type when available.

    This hack forces 'char(32)' to be used.  It allows UUID fields
    created and populated in the database prior to Django 5 to
    still work after switching to Django 5.  See 'Migrating existing
    UUIDField on MariaDB 10.7+' in the Django 5 release notes.

    Caveat: __iexact doesn't work with this field variant.  We haven't
    investigated why, but shouldn't be necessary anyway.
    """

    def db_type(self, connection):
        return "char(32)"

    def get_db_prep_value(self, value, connection, prepared=False):
        value = super().get_db_prep_value(value, connection, prepared)
        if value is not None:
            # Convert to 32 hex digit (no '-') format
            if type(value) is str:
                value = uuid.UUID(value)
            value = value.hex
        return value


class User(AbstractUser):
    sub = Char32UUIDField(null=True, unique=True)
    date_agreed_terms = models.DateTimeField(null=True)
    terms_version = models.IntegerField(default=0)


class FeatureOptions(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class FeatureManager(models.Manager):
    # feature_name is untrusted because it comes from the user, so
    # should be handled with care
    def get_feature_by_untrusted_feature_name(self, feature_app_name, user):
        # Get vm, and catch any errors
        try:
            feature = self.get(app_name=feature_app_name)
        except ValueError:
            logger.error(f"Value error trying to get a Feature with "
                         f"feature_name: {feature_app_name}, called by {user}")
            raise Http404
        except Feature.DoesNotExist:
            logger.error(f"Trying to get a Feature that doesn't exist with "
                         f"feature_name: {feature_app_name}, called by {user}")
            raise Http404
        return feature


class Feature(models.Model):
    name = models.CharField(max_length=50)
    options = models.ManyToManyField(FeatureOptions, blank=True)
    description = models.TextField()
    app_name = models.CharField(max_length=50, unique=True,
                                blank=True, null=True)
    currently_available = models.BooleanField(default=False)
    feature_or_service = models.BooleanField(default=True)
    auto_approved = models.BooleanField(default=False)
    beta = models.BooleanField(default=False)
    closed_beta = models.BooleanField(default=False)

    objects = FeatureManager()

    def __str__(self):
        return self.name


class ProjectManager(models.Manager):
    # project_id is untrusted because it comes from the user, so
    # should be handled with care
    def get_project_by_untrusted_project_id(self, project_id, user):
        # Get vm, and catch any errors
        try:
            project = self.get(id=project_id)
        except ValueError:
            logger.error(f"Value error trying to get a Project with "
                         f"project_id: {project_id}, called by {user}")
            raise Http404
        except Project.DoesNotExist:
            logger.error(f"Trying to get a Project that doesn't exist "
                         f"with project_id: {project_id}, called by {user}")
            raise Http404
        if project.project_admin != user:
            logger.error(f"Trying to get a Project that doesn't belong "
                         f"to {user} with project_id: {project_id}, "
                         f"this Project belongs to {project.project_admin}")
            raise Http404
        return project


class Project(models.Model):
    project_admin = models.ForeignKey(User, on_delete=models.PROTECT, )
    created = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=100)
    description = models.TextField()
    sensitive_data = models.BooleanField(default=False)
    FoR_code = models.CharField(max_length=6, choices=[])
    FoR_code2 = models.CharField(max_length=6, choices=[], blank=True)
    ARO = models.CharField(max_length=100, null=True, blank=True)
    ARO_approval = models.BooleanField(null=True, blank=True, )
    ARO_responded_on = models.DateTimeField(null=True, blank=True)
    chief_investigator = models.CharField(
        max_length=100, null=True, blank=True)
    permissions = models.ManyToManyField(
        Feature, through='Permission', through_fields=('project', 'feature'))
    additional_comments = models.TextField(null=True, blank=True)
    admin_comments = models.TextField(
        null=True, blank=True,
        verbose_name='Admin comments (not visible to users)')

    objects = ProjectManager()

    def accept(self, enable_default_features=True, auto_approved=False):
        self.ARO_approval = True
        self.ARO_responded_on = datetime.now(utc)
        self.save()
        if enable_default_features:
            for app_name in settings.PROJECT_DEFAULT_FEATURES:
                feature = Feature.objects.get(app_name=app_name)
                permission = Permission(project=self, feature=feature)
                permission.save()

        if not auto_approved:
            context = {'project': self}
            send_notification(self.project_admin,
                              'email/project_approved.html', context)

    def deny(self):
        self.ARO_approval = False
        self.ARO_responded_on = datetime.now(utc)
        self.save()
        context = {'project': self}
        send_notification(self.project_admin,
                          'email/project_declined.html', context)

    def __str__(self):
        return f"{self.title} ({self.project_admin})"

    def __init__(self, *args, **kwargs):
        super(Project, self).__init__(*args, **kwargs)
        self._meta.get_field('FoR_code').choices = FOR_CODE_CHOICES
        self._meta.get_field('FoR_code2').choices = FOR_CODE_CHOICES


class Permission(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, )
    feature = models.ForeignKey(Feature, on_delete=models.PROTECT, )
    feature_options = models.ManyToManyField(FeatureOptions, blank=True)

    def __str__(self):
        return f"{self.project} permission for {self.feature}"


def get_permission_feature_options_for_latest_project(user, feature):
    current_project = user.profile.get_last_selected_project()
    return Permission.objects.get(project=current_project, feature=feature) \
                             .feature_options.values_list('name', 'name')


class PermissionRequest(models.Model):
    requesting_user = models.ForeignKey(User, on_delete=models.PROTECT, )
    project = models.ForeignKey(Project, on_delete=models.PROTECT, )
    requested_feature = models.ForeignKey(Feature, on_delete=models.PROTECT,)
    feature_options = models.ManyToManyField(FeatureOptions, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    accepted = models.BooleanField(null=True, blank=True, )
    responded_on = models.DateTimeField(null=True, blank=True)

    def accept(self, auto_approved=False):
        if self.requested_feature in self.project.permissions.all():
            permission_feature_options = Permission.objects.get(
                project=self.project,
                feature=self.requested_feature).feature_options
            for feature_option in self.feature_options.all():
                permission_feature_options.add(feature_option)
        else:
            permission = Permission(project=self.project,
                                    feature=self.requested_feature)
            permission.save()
            permission.feature_options.set(self.feature_options.all())
        self.accepted = True
        self.responded_on = datetime.now(utc)
        self.save()

        if not auto_approved:
            context = {'feature': self}
            send_notification(self.requesting_user,
                              'email/feature_approved.html', context)

    def deny(self):
        self.accepted = False
        self.responded_on = datetime.now(utc)
        self.save()

        context = {'feature': self}
        send_notification(self.requesting_user,
                          'email/feature_declined.html', context)

    def __str__(self):
        return (f"Permission Request for {self.project} requesting "
                "{self.requested_feature}")


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    last_selected_project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True)
    timezone = models.CharField(max_length=100, blank=True)

    def get_last_selected_project(self):
        last_selected = self.last_selected_project
        if last_selected and last_selected.project_admin == self.user \
           and last_selected.ARO_approval:
            return last_selected
        try:
            last_project = Project.objects.filter(project_admin=self.user,
                                                  ARO_approval=True) \
                                          .latest('created')
        except Project.DoesNotExist:
            return None
        self.set_last_selected_project(last_project)
        return last_project

    def set_last_selected_project(self, project):
        if project.project_admin == self.user and project.ARO_approval:
            self.last_selected_project = project
            self.save()

    def __str__(self):
        return f"Profile for {self.user.username}"


class AROWhitelistManager(models.Manager):
    def is_username_whitelisted(self, username):
        try:
            return AROWhitelist.objects.get(username=username)
        except AROWhitelist.DoesNotExist:
            return False


def add_username_to_whitelist(username, comment, permission_granted_by):
    whitelist = AROWhitelist(username=username, comment=comment,
                             permission_granted_by=permission_granted_by)
    whitelist.save()


def remove_username_from_whitelist(username):
    whitelist = AROWhitelist.objects.get(username=username)
    whitelist.delete()


class AROWhitelist(models.Model):
    username = models.CharField(max_length=100, unique=True)
    comment = models.TextField(null=True, blank=True)
    permission_granted_by = models.ForeignKey(User, on_delete=models.PROTECT, )
    created = models.DateTimeField(auto_now_add=True)

    objects = AROWhitelistManager()

    class Meta:
        verbose_name = 'ARO whitelist'
        verbose_name_plural = 'ARO whitelist'

    def __str__(self):
        return f"{self.username} is ARO whitelisted"
