import logging

from django.http import Http404

from researcher_desktop.constants import APP_NAME
from researcher_desktop.models import DesktopType, Domain, AvailabilityZone
from researcher_workspace.models import Feature
from vm_manager.utils.utils import get_nectar


logger = logging.getLogger(__name__)


def desktops_feature() -> Feature:
    return Feature.objects.get(app_name=APP_NAME)


def get_desktop_type(id, only_enabled=True) -> DesktopType:
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


def get_best_zone(email, desktop_type, chosen_zone=None) -> AvailabilityZone:
    # The current 'policy' is to choose from the restricted_to zones if
    # the desktop type is restricted.  Otherwise, try restricting based
    # the user's email domain.  Use the zone's weight and name to break ties.
    #
    # If we want to, we could  block users whose domain is not recognized.
    #
    # Another possibility might be to dispatch randomly, or based on some
    zones = desktop_type.restrict_to_zones.all()
    if zones.count():
        if chosen_zone:
            return zones.filter(enabled=True) \
                        .filter(name=chosen_zone).first()
        else:
            return zones.filter(enabled=True) \
                        .order_by('zone_weight', 'name').first()

    zones = AvailabilityZone.objects.filter(enabled=True)
    if chosen_zone:
        zones = zones.filter(name=chosen_zone)
    elif zones.count() > 1:
        # See if limiting based on the user's email domain helps
        domain_name = email.split('@', 2)[1]
        user_zones = zones.filter(domains__name=domain_name)
        if user_zones.count() > 0:
            zones = user_zones

    return zones.order_by('zone_weight', 'name').first()
