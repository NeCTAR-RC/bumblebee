from rest_framework import permissions

from api.authentication import ServiceAccount


class ServiceTokensReadOnly(permissions.BasePermission):
    """Restrict service token principals to safe (read-only) methods.

    Every current endpoint is a ReadOnlyModelViewSet, so this changes
    nothing today; it makes the read-only guarantee for machine
    credentials explicit rather than incidental, so that any future
    write endpoint is not silently available to service tokens.
    """

    message = 'Service tokens have read-only access.'

    def has_permission(self, request, view):
        if isinstance(request.user, ServiceAccount):
            return request.method in permissions.SAFE_METHODS
        return True
