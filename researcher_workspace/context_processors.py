import socket

from django.conf import settings


# noinspection PyUnusedLocal
def from_settings(request):
    if not hasattr(from_settings, 'env_name'):
        from_settings.env_name = settings.ENVIRONMENT_NAME if hasattr(
            settings,
            'ENVIRONMENT_NAME') else None
        from_settings.env_colour = settings.ENVIRONMENT_COLOR if hasattr(
            settings,
            'ENVIRONMENT_COLOR') else None
        if settings.DEBUG:
            if not from_settings.env_name:
                from_settings.env_name = f"Developing on {socket.gethostname()}"
            if not from_settings.env_colour:
                from_settings.env_colour = "green"
        else:
            from_settings.env_name = f'Production on {socket.gethostname()}'
            from_settings.env_colour = "red"
    return {
        'ENVIRONMENT_NAME': from_settings.env_name,
        'ENVIRONMENT_COLOR': from_settings.env_colour,
    }
