from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from researcher_desktop.models import DesktopType


@admin.register(DesktopType)
class DesktopTypeAdmin(admin.ModelAdmin):
    pass
