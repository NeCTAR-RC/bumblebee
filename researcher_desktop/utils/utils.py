import logging

from django.http import Http404

from researcher_desktop.constants import APP_NAME
from researcher_desktop.models import DesktopType, AvailabilityZone
from researcher_workspace.models import Feature


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


def get_best_zone(email, desktop_type, chosen_zone) -> AvailabilityZone:
    """Pick the best AZ for launching a desktop of the given type.

    The chosen_zone is the user's choice.  If None, then choose on
    the user's behalf.  The email is the user's email address.  If no
    AZ is suitable, raise Http404.  (The UI shouldn't offer the user
    the option to do this, but it could be done by crafting a URL.)
    """

    zone = do_get_best_zone(email, desktop_type, chosen_zone)
    if not zone:
        if chosen_zone:
            logger.error(f"Chosen AZ {chosen_zone} is unknown or "
                         "disallowed for this desktop type")
        else:
            logger.error("No AZs allowed for this desktop type")
        raise Http404
    return zone


def do_get_best_zone(email, desktop_type, chosen_zone) -> AvailabilityZone:
    # The current 'policy' is to choose from the restricted_to zones if
    # the desktop type is restricted.  Otherwise, try restricting based
    # the user's email domain.  Use the zone's weight and name to break ties.
    #
    # Another possibility might be to dispatch randomly, or based on some
    # measure of AZ "fullness".
    #
    # If we wanted to, we could block users whose domain is not recognized,
    # or from specific domains / regions; e.g. New Zealand.
    #
    # The logic of this fn should be consistent with get_applicable_zones
    # with respect to restricting access.
    zones = desktop_type.restrict_to_zones.all()
    if zones.count():
        zones = zones.filter(enabled=True).exclude(network_id=None)
        if chosen_zone:
            return zones.filter(name=chosen_zone).first()
        else:
            return zones.order_by('zone_weight', 'name').first()

    zones = AvailabilityZone.objects.filter(enabled=True) \
                                    .exclude(network_id=None)
    if chosen_zone:
        zones = zones.filter(name=chosen_zone)
    elif zones.count() > 1:
        # If there are multiple zones, use the user's email domain
        # to try to get a preferred zone
        domain_name = email.split('@', 2)[1]
        user_zones = zones.filter(domains__name=domain_name)
        if user_zones.count() > 0:
            zones = user_zones

    return zones.order_by('zone_weight', 'name').first()


def get_applicable_zones(desktop_type):
    "Get a list of AZ for launching a desktop."

    zones = desktop_type.restrict_to_zones.all()
    if not zones:
        zones = AvailabilityZone.objects.all()
    return list(zones.filter(enabled=True)
                .exclude(network_id=None)
                .order_by('zone_weight', 'name'))
