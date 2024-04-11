from django.contrib import admin

from researcher_desktop.models import DesktopType, AvailabilityZone, Domain


@admin.register(DesktopType)
class DesktopTypeAdmin(admin.ModelAdmin):
    list_filter = ('enabled',)
    ordering = ('id',)
    list_display = ('id', 'image_name', 'default_flavor_name', 'big_flavor_name', 'volume_size')


@admin.register(AvailabilityZone)
class AvailabilityZoneAdmin(admin.ModelAdmin):
    list_filter = ('enabled',)
    ordering = ('-zone_weight',)
    list_display = ('name', 'zone_weight', 'network_id')


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('name', 'zone',)
