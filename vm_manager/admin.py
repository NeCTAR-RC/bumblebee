from django.contrib import admin
from django.http import HttpResponseRedirect

from vm_manager.constants import VM_OKAY
from vm_manager.models import *
from vm_manager.utils.expiry import InstanceExpiryPolicy, \
    VolumeExpiryPolicy, BoostExpiryPolicy
from vm_manager.views import admin_delete_vm


def set_expiry(modelAdmin, request, queryset):
    for r in queryset:
        if isinstance(r, Instance):
            expiry = InstanceExpiryPolicy().initial_expiry()
        elif isinstance(r, Volume):
            expiry = VolumeExpiryPolicy().initial_expiry()
        elif isinstance(r, Resize):
            expiry = ResizeExpiryPolicy().initial_expiry()
        else:
            raise Exception(f"{r.__class_name__} not supported")
        r.set_expires(expiry)


def unset_expiry(modelAdmin, request, queryset):
    for r in queryset:
        r.set_expires(None)


class ExpirationAdmin(admin.ModelAdmin):
    list_filter = ['id', 'stage', 'stage_date']
    fields = ['expires', 'stage', 'stage_date']
    readonly_fields = ['id']
    ordering = ('-id', )

    list_display = (
        '__str__',
    )


class ResourceAdmin(admin.ModelAdmin):
    list_filter = [
        'created', 'deleted', 'error_flag', 'error_message',
        'user', 'marked_for_deletion']
    readonly_fields = ['id', 'created', 'expiration']
    ordering = ('-created', )
    actions = [set_expiry, unset_expiry]

    list_display = (
        '__str__',
        'user',
        'created',
        'deleted',
        'expiration',
        'error_flag',
        'error_message',
    )


class InstanceAdmin(ResourceAdmin):
    list_filter = ResourceAdmin.list_filter + [
        'boot_volume__image', 'boot_volume__operating_system',
        'boot_volume__requesting_feature']
    actions = ResourceAdmin.actions + ["admin_delete_selected_instances"]
    readonly_fields = ResourceAdmin.readonly_fields + [
        "boot_volume_fields"]

    list_display = ResourceAdmin.list_display + (
        'ip_address',
        'get_requesting_feature',
        'boot_volume',
    )

    def get_requesting_feature(self, obj):
        return obj.boot_volume.requesting_feature

    get_requesting_feature.short_description = 'requesting feature'

#    def has_delete_permission(self, request, obj=None):
#        if obj and isinstance(obj, Instance):
#            return not obj.marked_for_deletion
#        return False
#
#    delete_confirmation_template = \
#        "admin/vm_manager/instance/task/delete_confirmation.html"

#    def admin_delete_selected_instances(self, request, queryset):
#        for instance in queryset:
#            if not instance.deleted:
#                admin_delete_vm(instance.id)
#    admin_delete_selected_instances.short_description = \
#        "Delete instances and volumes from openstack and mark " \
#        "them as deleted in the db"


class InstanceInline(admin.StackedInline):
    model = Instance
    can_delete = True
    show_change_link = True
    fk_name = "boot_volume"
    readonly_fields = InstanceAdmin.readonly_fields.copy()
    readonly_fields.remove("boot_volume_fields")
    max_num = 0
    ordering = ("created", )


class VolumeAdmin(ResourceAdmin):
    list_filter = ResourceAdmin.list_filter + [
        'image', 'operating_system', 'flavor', 'requesting_feature',
        'ready', 'checked_in']
    inlines = (InstanceInline, )

#    def has_delete_permission(self, request, obj=None):
#        return False

    list_display = ResourceAdmin.list_display + (
        'operating_system',
        'image',
        'flavor',
        'requesting_feature',
        'hostname_id',
    )


class ResizeAdmin(admin.ModelAdmin):
    list_filter = [
        'instance__boot_volume__operating_system', 'reverted',
        'instance__deleted', 'requested', 'instance__user']
    readonly_fields = ('requested', 'expiration')
    ordering = ('-requested',)
    actions = [set_expiry, unset_expiry]
    list_display = (
        '__str__',
        'requested',
        'expiration',
        'reverted',
        'instance',
    )

#    def has_delete_permission(self, request, obj=None):
#        return False


class VMStatusAdmin(admin.ModelAdmin):
    list_filter = [
        'created', 'requesting_feature', 'operating_system',
        'status', 'instance__deleted', 'user']
    readonly_fields = ('created',)
    ordering = ('-created',)

    list_display = (
        '__str__',
        'user',
        'status',
        'created',
        'requesting_feature',
        'operating_system',
        'wait_time',
        'instance',
    )

    change_form_template = 'admin/vm_manager/vm_status/change_form.html'

    def response_change(self, request, obj):
        if "_set_vm_okay" in request.POST:
            obj.status = VM_OKAY
            obj.save()
            obj.instance.error_flag = None
            obj.instance.error_message = None
            obj.instance.save()
            obj.instance.boot_volume.error_flag = None
            obj.instance.boot_volume.error_message = None
            obj.instance.boot_volume.ready = True
            obj.instance.boot_volume.save()
            self.message_user(request, "VM Status set to VM_Okay")
            return HttpResponseRedirect(".")
        return super().response_change(request, obj)

#    def has_delete_permission(self, request, obj=None):
#        return False


admin.site.register(Instance, InstanceAdmin)
admin.site.register(Volume, VolumeAdmin)
admin.site.register(Resize, ResizeAdmin)
admin.site.register(VMStatus, VMStatusAdmin)
admin.site.register(Expiration, ExpirationAdmin)
admin.site.disable_action('delete_selected')
