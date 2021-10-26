import logging

from django.db import migrations

from django.conf import settings

logger = logging.getLogger(__name__)


class Migration(migrations.Migration):

    def addDesktopTypes(apps, schema_editor):
        DesktopType = apps.get_model('researcher_desktop', 'DesktopType')
        AvailabilityZone = apps.get_model('researcher_desktop',
                                          'AvailabilityZone')
        Domain = apps.get_model('researcher_desktop', 'Domain')

        if hasattr(settings, 'ZONES'):
            for z in settings.ZONES:
                (zone, _) = AvailabilityZone.objects.get_or_create(
                    name=z['name'], zone_weight=int(z['zone_weight']))
                for d in z.get('domains', []):
                    domain = Domain.objects.create(name=d, zone=zone)

        # This is a bit rough and ready.  It assumes that all of the initial
        # DesktopType objects in the (current) settings were present when
        # the 0002 migration ran.  It doesn't sync up the original fields.
        if hasattr(settings, 'DESKTOP_TYPES'):
            for dt in settings.DESKTOP_TYPES:
                try:
                    desktop_type = DesktopType.objects.get(id=dt['id'])
                    if 'restrict_to_zones' in dt:
                        for z in dt['restrict_to_zones']:
                            desktop_type.restrict_to_zones.add(
                                AvailabilityZone.objects.get(name=z))
                except DesktopType.DoesNotExist:
                    logger.warning(
                        f"Missing desktop type {dt['id']}.  Create it "
                        "by hand and rerun this migration?")

    def removeDesktopTypes(apps, schema_editor):
        DesktopType = apps.get_model('researcher_desktop', 'DesktopType')
        DesktopType.objects.all().delete()

    dependencies = [
        ('researcher_desktop', '0003_add_availability_zones'),
    ]

    operations = [
        migrations.RunPython(addDesktopTypes, removeDesktopTypes)
    ]
