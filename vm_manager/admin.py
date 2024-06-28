from admin_searchable_dropdown.filters import AutocompleteFilterFactory
from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.formats import localize
from django.utils.safestring import mark_safe
from django.utils.timezone import localtime
from django_admin_listfilter_dropdown.filters import DropdownFilter


from vm_manager.constants import VM_OKAY, NO_VM
from vm_manager.models import Instance, Volume, Resize, Expiration, VMStatus
from vm_manager.utils.expiry import InstanceExpiryPolicy, \
    VolumeExpiryPolicy, BoostExpiryPolicy
from vm_manager.vm_functions.admin_functionality import \
    admin_delete_instance_and_volume, admin_delete_volume, \
    admin_archive_instance_and_volume, admin_archive_volume, \
    admin_shelve_instance, admin_downsize_resize, \
    admin_repair_volume_error, admin_repair_instance_error, \
    admin_check_vmstatus


def set_expiry(modelAdmin, request, queryset):
    for resource in queryset:
        if isinstance(resource, Instance):
            expiry = InstanceExpiryPolicy().initial_expiry()
        elif isinstance(resource, Volume):
            expiry = VolumeExpiryPolicy().initial_expiry()
        elif isinstance(resource, Resize):
            expiry = BoostExpiryPolicy().initial_expiry()
        else:
            raise Exception(f"{resource.__class_name__} not supported")
        resource.set_expires(expiry)


def clear_expiry(modelAdmin, request, queryset):
    for resource in queryset:
        resource.set_expires(None)


def admin_downsize_resizes(modelAdmin, request, queryset):
    for resize in queryset:
        if not resize.reverted:
            admin_downsize_resize(request, resize)


def admin_delete_instances(modelAdmin, request, queryset):
    for instance in queryset:
        if not instance.boot_volume.deleted:
            admin_delete_instance_and_volume(request, instance)


def admin_archive_instances(modelAdmin, request, queryset):
    for instance in queryset:
        if not instance.boot_volume.deleted:
            admin_archive_instance_and_volume(request, instance)


def admin_repair_volume_errors(modelAdmin, request, queryset):
    for volume in queryset:
        if not volume.marked_for_deletion and not volume.deleted:
            admin_repair_volume_error(request, volume)


def admin_delete_shelved_volumes(modelAdmin, request, queryset):
    for volume in queryset:
        if volume.shelved_at and not volume.deleted:
            admin_delete_volume(request, volume)


def admin_archive_shelved_volumes(modelAdmin, request, queryset):
    for volume in queryset:
        if volume.shelved_at and not volume.deleted:
            admin_archive_volume(request, volume)


def admin_shelve_instances(modelAdmin, request, queryset):
    for instance in queryset:
        if not instance.deleted:
            admin_shelve_instance(request, instance)


def admin_delete_shelved_instances(modelAdmin, request, queryset):
    for instance in queryset:
        if instance.deleted and instance.boot_volume.shelved_at:
            admin_delete_volume(request, instance.boot_volume)


def admin_repair_instance_errors(modelAdmin, request, queryset):
    for instance in queryset:
        if not instance.marked_for_deletion and not instance.deleted:
            admin_repair_instance_error(request, instance)


def admin_check_vmstatuses(modelAdmin, request, queryset):
    for vmstatus in queryset:
        admin_check_vmstatus(request, vmstatus)


@admin.register(Expiration)
class ExpirationAdmin(admin.ModelAdmin):
    list_filter = [('id', DropdownFilter), ('stage', DropdownFilter), 'stage_date']
    fields = ['expires', 'stage', 'stage_date']
    readonly_fields = ['id']
    ordering = ('-id',)
    list_display = ('id', 'expires', 'stage', 'stage_date')

    def has_delete_permission(self, request, obj=None):
        return settings.DEBUG


class Expirable(object):
    "Mixin class that provides rendering of an expiration field."

    def expiration_link(self, obj):
        if obj.expiration:
            return mark_safe(
                '<div style="white-space: nowrap">{}</div>'
                '<br><a href="{}" class="button">Open</a>'.format(
                    localize(localtime(obj.expiration.expires)),
                    reverse("admin:vm_manager_expiration_change",
                            args=(obj.expiration.pk,))
                ))
        else:
            return 'None'

    expiration_link.short_description = 'expiration'


class ResourceAdmin(admin.ModelAdmin, Expirable):
    list_filter = ['created', 'deleted', 'error_flag',
                   ('error_message', DropdownFilter),
                   AutocompleteFilterFactory('User', 'user'),
                   'marked_for_deletion']
    readonly_fields = ['id', 'created', 'expiration_link']
    ordering = ('-created',)
    actions = [set_expiry, clear_expiry]

    list_display = (
        'id',
        'user',
        'created',
        'deleted',
        'expiration_link',
        'error_flag',
        'error_message',
    )


@admin.register(Instance)
class InstanceAdmin(ResourceAdmin):
    list_filter = ResourceAdmin.list_filter + [
        ('boot_volume__image', DropdownFilter),
        ('boot_volume__operating_system', DropdownFilter),
        'boot_volume__requesting_feature']
    actions = ResourceAdmin.actions + [
        admin_delete_instances, admin_shelve_instances,
        admin_archive_instances, admin_delete_shelved_instances,
        admin_repair_instance_errors]
    readonly_fields = ResourceAdmin.readonly_fields + [
        "boot_volume_fields"]

    list_display = ResourceAdmin.list_display + (
        'ip_address',
        'get_requesting_feature',
        'boot_volume',
    )

    delete_confirmation_template = \
        "admin/vm_manager/instance/task/delete_confirmation.html"

    admin_shelve_instances.short_description = "Shelve instances"
    admin_repair_instance_errors.short_description = "Repair instance errors"
    admin_delete_instances.short_description = \
        "Delete instances and associated volumes"
    admin_archive_instances.short_description = \
        "Archive instances and associated volumes"
    admin_delete_shelved_instances.short_description = \
        "Delete volumes for shelved instances"

    def get_requesting_feature(self, obj):
        return obj.boot_volume.requesting_feature

    get_requesting_feature.short_description = 'requesting feature'

    def has_delete_permission(self, request, obj=None):
        if obj and isinstance(obj, Instance):
            return not obj.marked_for_deletion
        return settings.DEBUG


class InstanceInline(admin.StackedInline):
    model = Instance
    can_delete = True
    show_change_link = True
    fk_name = "boot_volume"
    readonly_fields = InstanceAdmin.readonly_fields.copy()
    readonly_fields.remove("boot_volume_fields")
    readonly_fields.remove("expiration_link")
    max_num = 0
    ordering = ("created",)


@admin.register(Volume)
class VolumeAdmin(ResourceAdmin):
    list_filter = ResourceAdmin.list_filter + [
        ('image', DropdownFilter),
        ('operating_system', DropdownFilter),
        'flavor', 'requesting_feature', 'ready', 'checked_in']
    actions = ResourceAdmin.actions + [
        admin_archive_shelved_volumes, admin_delete_shelved_volumes,
        admin_repair_volume_errors]
    inlines = (InstanceInline,)

    list_display = ResourceAdmin.list_display + (
        'operating_system',
        'image',
        'flavor',
        'requesting_feature',
        'hostname_id',
    )
    admin_delete_shelved_volumes.short_description = \
        "Delete volumes for shelved instances"
    admin_archive_shelved_volumes.short_description = \
        "Archive volumes for shelved instances"
    admin_repair_volume_errors.short_description = "Repair volume errors"

    def has_delete_permission(self, request, obj=None):
        return settings.DEBUG


@admin.register(Resize)
class ResizeAdmin(admin.ModelAdmin, Expirable):
    list_filter = [
        ('instance__boot_volume__operating_system', DropdownFilter),
        'reverted',
        'instance__deleted', 'requested',
        AutocompleteFilterFactory('User', 'instance__user')]

    readonly_fields = ('requested', 'expiration_link')
    ordering = ('-requested',)
    actions = [set_expiry, clear_expiry, admin_downsize_resizes]
    list_display = (
        '__str__',
        'requested',
        'expiration_link',
        'reverted',
        'instance',
    )
    admin_downsize_resizes.short_description = \
        "Downsize supersized instances"

    def has_delete_permission(self, request, obj=None):
        return settings.DEBUG


@admin.register(VMStatus)
class VMStatusAdmin(admin.ModelAdmin):
    list_filter = [
        'created', 'requesting_feature', 'operating_system',
        'status', 'instance__deleted',
        AutocompleteFilterFactory('User', 'user')]
    readonly_fields = ('created', 'id')
    ordering = ('-created',)
    actions = ResourceAdmin.actions + [admin_check_vmstatuses]

    list_display = (
        '__str__',
        'user',
        'status',
        'created',
        'operating_system',
        'wait_time',
        'instance',
    )

    change_form_template = 'admin/vm_manager/vm_status/change_form.html'
    admin_check_vmstatuses.short_description = "Check"

    def response_change(self, request, obj):
        if "_set_vm_okay" in request.POST:
            if obj.instance:
                # TODO - reassess this.  Just resetting all of the error
                # flags is not going to fix any underlying problems.
                # We should (at least) do some sanity checks on the
                # instance and volume first.
                obj.status = VM_OKAY
                obj.save()
                obj.instance.error_flag = None
                obj.instance.error_message = None
                obj.instance.save()
                obj.instance.boot_volume.error_flag = None
                obj.instance.boot_volume.error_message = None
                obj.instance.boot_volume.ready = True
                obj.instance.boot_volume.save()
            else:
                # If the 'instance' link wasn't set (or has been broken)
                # the best we can do is mark the VMStatus record as no
                # longer relevant.  If we mark it as OK, it makes problems
                # elsewhere.
                obj.status = NO_VM
                obj.save()
            self.message_user(request, "VM Status set to {obj.status}")
            return HttpResponseRedirect(".")
        return super().response_change(request, obj)

    def has_delete_permission(self, request, obj=None):
        return settings.DEBUG


admin.site.disable_action('delete_selected')
