import logging

from django.core.management.base import BaseCommand

from researcher_desktop.utils.utils import desktops_feature
from vm_manager.utils.expirer import VolumeExpirer, InstanceExpirer, \
    ResizeExpirer, ArchiveExpirer

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run a cronjob'

    def add_arguments(self, parser):
        parser.add_argument('--shelve', action='store_true',
                            help='Run the shelve job')
        parser.add_argument('--downsize', action='store_true',
                            help='Run the downsize job')
        parser.add_argument('--archive', action='store_true',
                            help='Run the archive job')
        parser.add_argument('--delete-archives', action='store_true',
                            help='Run the archive deletion job')
        parser.add_argument('--dry-run', action='store_true',
                            help='Only count the affected objects')
        parser.add_argument('--verbose', action='store_true',
                            help='In dry-run mode, output the emails')

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.verbose = options['verbose']
        if self.dry_run:
            print("Running in --dry-run mode: affected objects "
                  "will only be counted")
        if options['shelve']:
            self.shelve_job()
        if options['downsize']:
            self.downsize_job()
        if options['archive']:
            self.archive_job()
        if options['delete_archives']:
            self.delete_archives_job()

    def downsize_job(self):
        feature = desktops_feature()
        logger.info("Starting boost expiry")
        expirer = ResizeExpirer(dry_run=self.dry_run, verbose=self.verbose)
        counts = expirer.run(feature)
        logger.info(f"Downsizing counts: {counts}")

    def shelve_job(self):
        feature = desktops_feature()
        logger.info("Starting instance expiry")
        expirer = InstanceExpirer(dry_run=self.dry_run, verbose=self.verbose)
        counts = expirer.run(feature)
        logger.info(f"Shelving counts: {counts}")

    def archive_job(self):
        feature = desktops_feature()
        logger.info(f"Starting volume archiving")
        expirer = VolumeExpirer(dry_run=self.dry_run, verbose=self.verbose)
        counts = expirer.run(feature)
        logger.info(f"Archiving counts: {counts}")

    def delete_archives_job(self):
        feature = desktops_feature()
        logger.info(f"Starting archive deletions")
        expirer = ArchiveExpirer(dry_run=self.dry_run, verbose=self.verbose)
        counts = expirer.run(feature)
        logger.info(f"Archive deletion counts: {counts}")
