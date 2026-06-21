import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from vm_manager.models import Instance, Volume, VMStatus
from vm_manager.utils.utils import get_nectar

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = ("Audit discrepancies between the Bumblebee database and "
            "OpenStack.\n\n"
            "Compares the desktop Volume and Instance records against the "
            "volumes and servers that actually exist in OpenStack, and "
            "reports, for both volumes and instances:\n"
            "  * records that the database expects to exist (not deleted) "
            "but that are missing from OpenStack;\n"
            "  * records that the database has marked as deleted but that "
            "still exist in OpenStack (leaked resources); and\n"
            "  * OpenStack resources tagged as belonging to this "
            "environment that have no database record (untracked).\n\n"
            "Database and OpenStack credentials are taken from the Django "
            "settings, i.e. the same configuration the application uses.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--environment',
            help="Override the environment name used to identify Bumblebee's "
                 "OpenStack resources (defaults to "
                 "settings.ENVIRONMENT_NAME).")

    def handle(self, *args, **options):
        environment = options['environment'] or settings.ENVIRONMENT_NAME
        if not environment:
            self.stderr.write(self.style.WARNING(
                "No environment name set (settings.ENVIRONMENT_NAME is "
                "empty). Untracked-resource detection cannot filter to "
                "Bumblebee's resources and is skipped."))

        self.stdout.write(self.style.MIGRATE_HEADING(
            "OpenStack <-> DB audit"))
        self.stdout.write(f"Environment: {environment or '(unset)'}")

        self.stdout.write("\nFetching database state...")
        db_volumes = self.collect_db_volumes()
        db_instances = self.collect_db_instances()
        vm_statuses = self.collect_vm_statuses()
        db_live_volumes = sum(
            1 for v in db_volumes.values() if not self.is_deleted(v))
        db_live_instances = sum(
            1 for i in db_instances.values() if not self.is_deleted(i))
        self.stdout.write(
            f"  Volumes:   {len(db_volumes)} (live {db_live_volumes}, "
            f"deleted {len(db_volumes) - db_live_volumes})")
        self.stdout.write(
            f"  Instances: {len(db_instances)} (live {db_live_instances}, "
            f"deleted {len(db_instances) - db_live_instances})")

        self.stdout.write("\nConnecting to OpenStack...")
        n = get_nectar()
        os_volumes = {v.id: v for v in n.cinder.volumes.list()}
        os_servers = {s.id: s for s in n.nova.servers.list()}
        self.stdout.write(f"  Volumes: {len(os_volumes)}")
        self.stdout.write(f"  Servers: {len(os_servers)}")

        summary = {}
        summary.update(
            self.audit_volumes(db_volumes, os_volumes, environment))
        summary.update(
            self.audit_instances(
                db_instances, os_servers, vm_statuses, environment))

        self.stdout.write(self.style.MIGRATE_HEADING("\nSummary"))
        total = 0
        for label, count in summary.items():
            self.stdout.write(f"  {label}: {count}")
            total += count
        style = self.style.ERROR if total else self.style.SUCCESS
        self.stdout.write(style(f"  total discrepancies: {total}"))

    def collect_db_volumes(self):
        """Return {volume_id: Volume} for every Volume record."""
        return {str(v.id): v
                for v in Volume.objects.select_related('user').all()}

    def collect_db_instances(self):
        """Return {instance_id: Instance} for every Instance record."""
        return {str(i.id): i
                for i in Instance.objects.select_related(
                    'user', 'boot_volume').all()}

    def collect_vm_statuses(self):
        """Return {instance_id: latest VMStatus status} for context."""
        statuses = {}
        for vs in VMStatus.objects.filter(
                instance__isnull=False).order_by('created'):
            # Ordered oldest first, so the last write wins => latest status.
            statuses[str(vs.instance_id)] = vs.status
        return statuses

    def is_deleted(self, record):
        """A record is 'deleted' from the app's point of view if it has a
        deleted timestamp set."""
        return record.deleted is not None

    def annotate(self, record):
        """Build a short annotation of a DB record's flags for the report."""
        flags = []
        if record.marked_for_deletion is not None:
            flags.append('marked_for_deletion')
        if record.error_flag is not None:
            flags.append('error')
        return f" [{', '.join(flags)}]" if flags else ''

    def belongs_to_environment(self, os_resource, environment):
        """Whether an OpenStack resource is tagged for this Bumblebee
        environment.  Bumblebee stamps an 'environment' metadata key on the
        volumes and servers it creates."""
        metadata = getattr(os_resource, 'metadata', None) or {}
        return metadata.get('environment') == environment

    def print_section(self, title, lines):
        self.stdout.write(f"\n--- {title} ({len(lines)}) ---")
        for line in lines:
            self.stdout.write(f"  {line}")
        if not lines:
            self.stdout.write("  (none)")

    def audit_volumes(self, db_volumes, os_volumes, environment):
        """Compare DB volumes against OpenStack volumes; return a summary."""
        missing = []
        leaked = []
        for vol_id, vol in sorted(db_volumes.items()):
            present = vol_id in os_volumes
            desc = (f"{vol_id}  os={vol.operating_system} "
                    f"user={vol.user}{self.annotate(vol)}")
            if not self.is_deleted(vol) and not present:
                missing.append(desc)
            elif self.is_deleted(vol) and present:
                leaked.append(
                    f"{desc}  cinder_status={os_volumes[vol_id].status}")

        untracked = []
        for os_id, os_vol in sorted(os_volumes.items()):
            if os_id in db_volumes:
                continue
            if environment and not self.belongs_to_environment(
                    os_vol, environment):
                continue
            untracked.append(f"{os_id}  name={os_vol.name} "
                             f"cinder_status={os_vol.status}")

        self.print_section("DB volumes missing from OpenStack "
                            "(live in DB, absent in Cinder)", missing)
        self.print_section(
            "Deleted DB volumes still in OpenStack (leaked)", leaked)
        self.print_section(f"OpenStack volumes not tracked in DB "
                           f"(environment={environment})", untracked)
        return {
            'volumes missing from OpenStack': len(missing),
            'deleted volumes still in OpenStack': len(leaked),
            'untracked OpenStack volumes': len(untracked),
        }

    def audit_instances(self, db_instances, os_servers, vm_statuses,
                        environment):
        """Compare DB instances against OpenStack servers; return a summary."""
        missing = []
        leaked = []
        for inst_id, inst in sorted(db_instances.items()):
            present = inst_id in os_servers
            status = vm_statuses.get(inst_id, '?')
            desc = (f"{inst_id}  user={inst.user} "
                    f"vm_status={status}{self.annotate(inst)}")
            if not self.is_deleted(inst) and not present:
                missing.append(desc)
            elif self.is_deleted(inst) and present:
                leaked.append(
                    f"{desc}  nova_status={os_servers[inst_id].status}")

        untracked = []
        for os_id, server in sorted(os_servers.items()):
            if os_id in db_instances:
                continue
            if environment and not self.belongs_to_environment(
                    server, environment):
                continue
            untracked.append(f"{os_id}  name={server.name} "
                            f"nova_status={server.status}")

        self.print_section("DB instances missing from OpenStack "
                            "(live in DB, absent in Nova)", missing)
        self.print_section(
            "Deleted DB instances still in OpenStack (leaked)", leaked)
        self.print_section(f"OpenStack servers not tracked in DB "
                           f"(environment={environment})", untracked)
        return {
            'instances missing from OpenStack': len(missing),
            'deleted instances still in OpenStack': len(leaked),
            'untracked OpenStack servers': len(untracked),
        }
