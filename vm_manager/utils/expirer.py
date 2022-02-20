import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.utils.timezone import utc

from researcher_workspace.utils import send_notification, format_notification
from researcher_desktop.models import DesktopType
from vm_manager.models import Instance, Volume, Resize
from vm_manager.vm_functions.shelve_vm import shelve_expired_vm
from vm_manager.vm_functions.archive_vm import archive_expired_vm
from vm_manager.vm_functions.resize_vm import downsize_expired_vm

logger = logging.getLogger(__name__)

EXP_INITIAL = 0
EXP_FIRST_WARNING = 1
EXP_FINAL_WARNING = 2
EXP_EXPIRED = 3


def days(days):
    return timedelta(days=days) if days and days > 0 else None


class Expirer(object):
    '''An Expirer is designed to be called periodically to send expiry
    warnings, and finally to perform the expiration action.  This class
    is implements a 4-stage state machine:
     - In stage EXP_INITIAL, we are waiting for the time to send the first
       warning.
     - In stage EXP_FIRST_WARNING, we send the first warning (if any) and
       wait until it is time to send the final warning
     - In stage EXP_FINAL_WARNING, we send the final warning (if any) and
       wait until it is time to expire the resource.
     - In stage EXP_EXPIRED, we perform the expiration action.
    The expiry data and stage are held in a resource's Expiration object.
    When the stage changes, the 'stage_date' is updated.  We also adjust
    expiry, so that of the Expirer does a notification stage late, the user
    will still get the configured number of notices, and time between notices
    and ultimate expiration.

    The Expirer supports a dry-run mode in which notifications are not sent,
    resources are not expired and the stages are not updated.

    This class is responsible for performing the staging for individual
    resources when 'do_stage' is called.  Child classes offer a 'run' method
    that iterates all of its resources in expirable state.  They must also
    implement a 'do_expire' callback to perform the expiration action, and
    an 'add_target_details' callback that populates a 'context' with details
    of a resource.
    '''

    def __init__(self, template, dry_run=False, verbose=False,
                 first_warning=None, final_warning=None):
        self.template = template
        self.dry_run = dry_run
        self.verbose = verbose
        if first_warning and not final_warning:
            raise Exception("Config error: first warning w/o final warning")
        self.first_warning = first_warning
        self.final_warning = final_warning
        self.now = datetime.now(utc)

    def notify(self, user, context):
        if not self.dry_run:
            send_notification(user, self.template, context)
        elif self.verbose:
            text = format_notification(user, self.template, context)
            print(f"email: {user.email}\nsubject: {text}")

    def do_stage(self, target, expiration, user) -> int:
        # TODO - rather than returning an 'int' (zero or one), return
        # something that distinguishes the action performed in a way
        # that allows the called to provide more meaningful statistics.

        logger.debug(f"do_stage for {self}, {target}, {expiration}, {user}")
        stage = None
        if expiration.stage == EXP_INITIAL:
            if self.first_warning:
                if expiration.expires - self.first_warning <= self.now:
                    stage = EXP_FIRST_WARNING
                    remaining = self.first_warning
            elif self.final_warning:
                if expiration.expires - self.final_warning <= self.now:
                    stage = EXP_FINAL_WARNING
                    remaining = self.final_warning
            else:
                # No warnings ...
                stage = EXP_EXPIRED
                remaining = timedelta(seconds=0)
        elif expiration.stage == EXP_FIRST_WARNING:
            if expiration.expires - self.final_warning <= self.now:
                stage = EXP_FINAL_WARNING
                remaining = self.final_warning
        elif expiration.stage == EXP_FINAL_WARNING:
            if expiration.expires <= self.now:
                stage = EXP_EXPIRED
                remaining = timedelta(seconds=0)
        logger.debug(f"Stage is {stage}")
        if stage:
            if stage in [EXP_FIRST_WARNING, EXP_FINAL_WARNING]:
                context = {
                    'warning': ('first' if stage == EXP_FIRST_WARNING
                                else 'final'),
                    'expires': expiration.expires,
                    'adjusted': self.now + remaining,
                    'remaining': remaining
                }
                self.add_target_details(target, context)
                self.notify(user, context)
            elif stage == EXP_EXPIRED:
                if not self.dry_run:
                    if not self.do_expire(target):
                        logger.error(f"Expiration action failed for {target}")
                        # Don't update the expiration record!
                        return 0
                else:
                    logger.error(f"Would have expired {target}")
            if not self.dry_run:
                expiration.stage = stage
                expiration.stage_date = self.now
                expiration.expires = self.now + remaining
                expiration.save()
            else:
                logger.debug(f"Would have updated expiration for {target} "
                             f"to stage {stage}, stage_date {self.now}")
            return 1
        else:
            return 0


class VolumeExpirer(Expirer):
    '''This expirer archives shelved instances
    '''

    def __init__(self, **kwargs):
        super().__init__('email/volume_expiry.html',
                         first_warning=days(settings.VOLUME_WARNING_1),
                         final_warning=days(settings.VOLUME_WARNING_2),
                         **kwargs)

    def run(self, feature):
        count = 0
        for v in Volume.objects.exclude(expiration=None) \
                               .filter(deleted=None,
                                       marked_for_deletion=None) \
                               .prefetch_related('expiration', 'user'):
            count += self.do_stage(v, v.expiration, v.user)
        return count

    def do_expire(self, volume):
        return archive_expired_vm(volume, volume.requesting_feature)

    def add_target_details(self, volume, context):
        context['desktop_type'] = DesktopType.objects.get_desktop_type(
            volume.operating_system)
        context['volume'] = volume


class InstanceExpirer(Expirer):
    '''This expirer shelves instances
    '''

    def __init__(self, **kwargs):
        super().__init__('email/instance_expiry.html',
                         first_warning=days(settings.INSTANCE_WARNING_1),
                         final_warning=days(settings.INSTANCE_WARNING_2),
                         **kwargs)

    def run(self, feature):
        count = 0
        for i in Instance.objects.exclude(expiration=None) \
                                 .filter(deleted=None,
                                         marked_for_deletion=None) \
                                 .prefetch_related('expiration', 'user'):
            count += self.do_stage(i, i.expiration, i.user)
        return count

    def do_expire(self, instance):
        return shelve_expired_vm(instance,
                                 instance.boot_volume.requesting_feature)

    def add_target_details(self, instance, context):
        context['desktop_type'] = DesktopType.objects.get_desktop_type(
            instance.boot_volume.operating_system)
        context['instance'] = instance
        context['volume'] = instance.boot_volume


class ResizeExpirer(Expirer):
    '''This expirer downsizes boosted instances.
    '''

    def __init__(self, **kwargs):
        super().__init__('email/resize_expiry.html',
                         first_warning=days(settings.BOOST_WARNING_1),
                         final_warning=days(settings.BOOST_WARNING_2),
                         **kwargs)

    def run(self, feature):
        count = 0
        for r in Resize.objects.exclude(expiration=None) \
                               .filter(reverted=None,
                                       instance__marked_for_deletion=None,
                                       instance__deleted=None) \
                               .prefetch_related('expiration', 'instance'):
            count += self.do_stage(r, r.expiration, r.instance.user)
        return count

    def do_expire(self, resize):
        return downsize_expired_vm(
            resize,
            resize.instance.boot_volume.requesting_feature)

    def add_target_details(self, resize, context):
        context['desktop_type'] = DesktopType.objects.get_desktop_type(
            resize.instance.boot_volume.operating_system)
        context['resize'] = resize
        context['instance'] = resize.instance
        context['volume'] = resize.instance.boot_volume
