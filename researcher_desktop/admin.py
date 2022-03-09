from django.contrib import admin

from researcher_desktop.models import DesktopType, AvailabilityZone, Domain


@admin.register(DesktopType)
class DesktopTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(AvailabilityZone)
class AvailabilityZoneAdmin(admin.ModelAdmin):
    pass


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    pass
