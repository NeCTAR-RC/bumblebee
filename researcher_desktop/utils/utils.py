import logging

from django.http import Http404

from researcher_desktop.constants import APP_NAME
from researcher_desktop.models import DesktopType
from researcher_workspace.models import Feature
from vm_manager.utils.utils import get_nectar


logger = logging.getLogger(__name__)


def desktops_feature():
    return Feature.objects.get(app_name=APP_NAME)


def get_desktop_type(id, only_enabled=True):
    try:
        desktop_type = DesktopType.objects.get(id=id)
        if only_enabled and not desktop_type.enabled:
            logger.error(f"Disabled desktop({id}) requested")
            raise Http404
        return desktop_type
    except DesktopType.DoesNotExist:
        logger.error(f"Unknown desktop({id}) requested")
        raise Http404


def desktop_types():
    return DesktopType.objects.filter(enabled=True)
