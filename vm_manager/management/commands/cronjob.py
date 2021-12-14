import logging

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from researcher_desktop.utils.utils import desktops_feature
from vm_manager.vm_functions.resize_vm import downsize_expired_supersized_vms
from vm_manager.vm_functions.shelve_vm import shelve_expired_vms

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run a cronjob'

    def add_arguments(self, parser):
        parser.add_argument('--shelve', action='store_true',
                            help='Run the shelve job')
        parser.add_argument('--downsize', action='store_true',
                            help='Run the downsize job')

    def handle(self, *args, **options):
        if options['shelve']:
            self.shelve_job()
        if options['downsize']:
            self.downsize_job()

    def downsize_job(self):
        feature = desktops_feature()
        logger.info(f"Starting tasks to downsize expired boost instances "
                    f"of {feature}")
        count = downsize_expired_supersized_vms(feature)
        logger.info(f"Started downsizing {count} instances")

    def shelve_job(self):
        feature = desktops_feature()
        logger.info(f"Starting tasks to shelve expired instances of {feature}")
        count = shelve_expired_vms(feature)
        logger.info(f"Started shelving {count} instances")
