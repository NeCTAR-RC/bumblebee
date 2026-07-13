from django.contrib import admin

from api.models import ServiceToken


@admin.register(ServiceToken)
class ServiceTokenAdmin(admin.ModelAdmin):
    """Manage service tokens.

    Tokens are created with the 'create_service_token' management
    command, which is the only time the key is shown.  The admin is
    for auditing and revocation (deactivate or delete).
    """

    list_display = ('name', 'prefix', 'created', 'last_used', 'active')
    fields = ('name', 'prefix', 'created', 'last_used', 'active')
    readonly_fields = ('prefix', 'created', 'last_used')

    def has_add_permission(self, request):
        # Keys must be generated (and shown once) via the
        # create_service_token management command.
        return False
