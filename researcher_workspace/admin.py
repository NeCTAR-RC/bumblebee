from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from researcher_workspace.models import PermissionRequest, Project, Profile, AROWhitelist, add_username_to_whitelist, \
    remove_username_from_whitelist, Permission, Feature, User


@admin.register(PermissionRequest)
class PermissionRequestAdmin(admin.ModelAdmin):
    list_filter = ('created', 'accepted', 'responded_on', 'requested_feature', 'requesting_user')
    readonly_fields = ('created',)
    ordering = ('-created',)
    list_display = ('__str__', 'accepted', 'requesting_user', 'project', 'requested_feature', 'created')
    actions = ["accept_requests", "deny_requests"]
    change_form_template = 'admin/researcher_workspace/permissionrequest/change_form.html'

    # def has_delete_permission(self, request, obj=None):
    #    return False

    def response_change(self, request, obj):
        if "_accept" in request.POST:
            obj.accept()
            self.message_user(request, "Permission request accepted and applied")
            return HttpResponseRedirect(".")
        if "_deny" in request.POST:
            obj.deny()
            self.message_user(request, "Permission request denied")
            return HttpResponseRedirect(".")
        return super().response_change(request, obj)

    def accept_requests(self, request, queryset):
        for request in queryset:
            if request.accepted is None:
                request.accept()
    accept_requests.short_description = "Add the requested permissions to the project"

    def deny_requests(self, request, queryset):
        for request in queryset:
            if request.accepted is None:
                request.deny()
    deny_requests.short_description = "Reject the request and don't give the requested permissions to the project"


class PermissionInline(admin.StackedInline):
    model = Permission
    can_delete = True
    fk_name = "project"
    extra = 1


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_filter = ('created', 'ARO_approval', 'ARO_responded_on', 'permissions', 'sensitive_data', 'project_admin', 'ARO')
    readonly_fields = ('created',)
    ordering = ('-created',)
    list_display = ('__str__', 'title', 'project_admin', 'created', 'ARO', 'ARO_approval')
    actions = ["approve_projects", "reject_projects"]
    change_form_template = 'admin/researcher_workspace/project/change_form.html'
    inlines = (PermissionInline, )

    # def has_delete_permission(self, request, obj=None):
    #    return False

    def response_change(self, request, obj):
        if "_accept" in request.POST:
            obj.accept()
            self.message_user(request, "Project accepted")
            return HttpResponseRedirect(".")
        if "_deny" in request.POST:
            obj.deny()
            self.message_user(request, "Project rejected")
            return HttpResponseRedirect(".")
        return super().response_change(request, obj)

    def approve_projects(self, request, queryset):
        for project in queryset:
            if project.ARO_approval is None:
                project.accept()
    approve_projects.short_description = "Mark projects as approved"

    def reject_projects(self, request, queryset):
        for project in queryset:
            if project.ARO_approval is None:
                project.deny()
    reject_projects.short_description = "Mark projects as rejected"


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'
    readonly_fields = ('aro_whitelisted',)

    def aro_whitelisted(self, instance):
        whitelist = AROWhitelist.objects.is_username_whitelisted(instance.user.username)
        if whitelist:
            return format_html(f"{ whitelist } <a class='button' href='{reverse('admin:researcher_workspace_arowhitelist_change', args=(whitelist.id,))}'>Edit</a>")
        else:
            return format_html(f"{ instance.user.username } is not ARO whitelisted <a class='button' href='{reverse('admin:researcher_workspace_arowhitelist_add')}?username={ instance.user.username }'>Add user to AROWhitelist</a>")


class CustomUserAdmin(UserAdmin):
    inlines = (ProfileInline, )
    list_filter = UserAdmin.list_filter + ('date_joined',)
    list_display = UserAdmin.list_display + ('date_joined',)
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser',
                       'groups', 'user_permissions'),
        }),
        (_('Important dates'), {
            'fields': ('last_login', 'date_joined', 'date_agreed_terms',
                       'terms_version')}),
    )

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super(CustomUserAdmin, self).get_inline_instances(request, obj)

    def response_change(self, request, obj):
        if "_add_to_whitelist" in request.POST:
            comment = request.POST.get('aro_whitelist_comment')
            add_username_to_whitelist(username=obj.username, comment=comment, permission_granted_by=request.user)
            self.message_user(request, "User added to ARO whitelist")
            return HttpResponseRedirect(".")
        if "_remove_from_whitelist" in request.POST:
            remove_username_from_whitelist(username=obj.username)
            self.message_user(request, "User removed from ARO whitelist")
            return HttpResponseRedirect(".")
        return super().response_change(request, obj)


# admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(AROWhitelist)
class AROWhitelistAdmin(admin.ModelAdmin):
    list_display = ('username', 'permission_granted_by', 'created', 'comment')
    list_filter = ('created', ('comment', admin.EmptyFieldListFilter), 'permission_granted_by', )
    actions = ['delete_selected']
    readonly_fields = ('created', 'permission_granted_by', )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super(AROWhitelistAdmin, self).get_readonly_fields(request, obj)
        if obj is not None:
            readonly_fields = ("username", ) + readonly_fields
        return readonly_fields

    def get_fields(self, request, obj=None):
        if obj is None:
            return ('username', 'comment', )
        else:
            return ('username', 'permission_granted_by', 'comment', 'created', )

    def save_model(self, request, obj, form, change):
        if not change:  # i.e. if this is a new model
            obj.permission_granted_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_filter = ['name', 'currently_available', 'feature_or_service', 'auto_approved', 'beta']
    readonly_fields = ('id', 'app_name')
    ordering = ('id',)

    list_display = (
        'name',
        'app_name',
        'view_feature_or_service',
        'currently_available',
        'auto_approved',
        'beta',
    )

    def view_feature_or_service(self, obj):
        if obj.feature_or_service:
            return 'Feature'
        else:
            return 'Service'

    view_feature_or_service.short_description = 'Feature/Service'

    # def has_delete_permission(self, request, obj=None):
    #    return False

    def save_model(self, request, obj, form, change):
        if 'name' in form.changed_data:
            messages.add_message(request, messages.WARNING, 'WARNING: Must restart apache for changes to the feature name to fully take effect')
        super(FeatureAdmin, self).save_model(request, obj, form, change)
