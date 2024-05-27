import logging
from datetime import datetime, timedelta, timezone

from django.conf import settings

from researcher_workspace.utils import send_notification, format_notification
from researcher_desktop.models import DesktopType
from vm_manager.constants import WF_SUCCESS, WF_CONTINUE, WF_RETRY, WF_FAIL
from vm_manager.models import Instance, Volume, Resize, \
    EXP_INITIAL, EXP_FIRST_WARNING, EXP_FINAL_WARNING, EXP_EXPIRING, \
    EXP_EXPIRY_COMPLETED, EXP_EXPIRY_FAILED, EXP_EXPIRY_FAILED_RETRYABLE
from vm_manager.vm_functions.delete_vm import \
    archive_expired_volume, delete_backup_worker
from vm_manager.vm_functions.resize_vm import downsize_expired_vm
from vm_manager.vm_functions.shelve_vm import shelve_expired_vm

logger = logging.getLogger(__name__)

#
# These are the possible responses from do_stage or from a
# do_expire callback.
#

# Action completed
EXP_SUCCESS = WF_SUCCESS

# User notified
EXP_NOTIFY = 'notified'

# Action started but not completed.  Continues in the background
EXP_STARTED = WF_CONTINUE

# Action failed - retryable
EXP_RETRY = WF_RETRY

# Action failed - non-retryable
EXP_FAIL = WF_FAIL

# Action skipped; e.g. because we are not ready to expire it yet, or
# the expiry is already running.
EXP_SKIP = 'skipped'


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

    def __init__(self, template, first_warning=None, final_warning=None,
                 dry_run=False, verbose=False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.now = datetime.now(timezone.utc)
        self.template = template
        if first_warning and not final_warning:
            raise Exception("Config error: first warning w/o final warning")
        self.first_warning = first_warning
        self.final_warning = final_warning
        self.counts = {}

    def accumulate(self, outcome):
        if outcome in self.counts:
            self.counts[outcome] = self.counts[outcome] + 1
        else:
            self.counts[outcome] = 1

    def notify(self, user, context):
        if not self.dry_run:
            send_notification(user, self.template, context)
        elif self.verbose:
            text = format_notification(user, self.template, context)
            print(f"email: {user.email}\nsubject: {text}")

    def do_stage(self, target, expiration, user) -> str:
        """Returns one of EXP_SUCCESS, EXP_STARTED, EXP_RETRY, EXP_FAIL
        or EXP_SKIP to indicate the outcome.
        """

        logger.debug(f"do_stage for {self}, {target}, {expiration}, {user}")
        stage = None
        if expiration.stage == EXP_EXPIRING:
            logger.warning(
                f"Expiration already running for {expiration}: skip")
            return EXP_SKIP
        elif expiration.stage in (EXP_EXPIRY_COMPLETED, EXP_EXPIRY_FAILED):
            logger.error(
                "Expiration stage wrong: "
                f"{self}, {target}, {expiration}, {user}: skip")
            return EXP_SKIP
        elif expiration.stage == EXP_INITIAL:
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
                stage = EXP_EXPIRING
                remaining = timedelta(seconds=0)
        elif expiration.stage == EXP_FIRST_WARNING:
            if expiration.expires - self.final_warning <= self.now:
                stage = EXP_FINAL_WARNING
                remaining = self.final_warning
        elif expiration.stage == EXP_FINAL_WARNING:
            if expiration.expires <= self.now:
                stage = EXP_EXPIRING
                remaining = timedelta(seconds=0)
        else:
            logger.warning(f"Retrying expiry for {target}")
            stage = EXP_EXPIRING
            remaining = timedelta(seconds=0)

        logger.debug(f"Stage {expiration.stage} -> {stage}")
        res = None
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
                res = EXP_NOTIFY
            elif stage == EXP_EXPIRING:
                if not self.dry_run:
                    res = self.do_expire(target)
                    if res in (EXP_FAIL, EXP_RETRY):
                        logger.error(f"Expiration action failed ({res})"
                                     f" for {target}")
                    if res == EXP_SUCCESS:
                        stage = EXP_EXPIRY_COMPLETED
                    elif res == EXP_FAIL:
                        stage = EXP_EXPIRY_FAILED
                    elif res == EXP_RETRY:
                        stage = EXP_EXPIRY_FAILED_RETRYABLE
                    elif res == EXP_STARTED:
                        stage = EXP_EXPIRING
                else:
                    # Pretend it would have worked
                    res = EXP_SUCCESS
                    logger.info(f"Would have expired {target}")
            if not (self.dry_run or res == EXP_SKIP):
                logger.debug(f"Stage persisted as {stage}")
                expiration.stage = stage
                expiration.stage_date = self.now
                expiration.expires = self.now + remaining
                expiration.save()
            else:
                logger.debug(f"Would have updated expiration for {target} "
                             f"to stage {stage}, stage_date {self.now}")
        logger.debug(f"do_stage returning {res}")
        return res or EXP_SKIP


class VolumeExpirer(Expirer):
    '''This expirer archives shelved instances
    '''

    def __init__(self, **kwargs):
        super().__init__('email/volume_expiry.html',
                         first_warning=days(settings.VOLUME_WARNING_1),
                         final_warning=days(settings.VOLUME_WARNING_2),
                         **kwargs)

    def run(self, feature):
        for v in Volume.objects.exclude(expiration=None) \
                               .filter(deleted=None,
                                       marked_for_deletion=None) \
                               .prefetch_related('expiration', 'user'):
            self.accumulate(self.do_stage(v, v.expiration, v.user))
        return self.counts

    def do_expire(self, volume):
        return archive_expired_volume(volume, volume.requesting_feature)

    def add_target_details(self, volume, context):
        context['desktop_type'] = DesktopType.objects.get_desktop_type(
            volume.operating_system)
        context['volume'] = volume


class ArchiveExpirer(Expirer):
    '''This expirer deletes archives (backups) for archived volumes.
    Note that this doesn't need to do notification and staging, and
    doesn't have an associated Expiration record.
    '''

    def __init__(self, **kwargs):
        super().__init__(None, **kwargs)

    def run(self, feature):
        for v in Volume.objects \
                       .exclude(backup_expiration=None) \
                       .exclude(backup_expiration__stage__in=[
                           EXP_EXPIRY_COMPLETED, EXP_EXPIRY_FAILED]) \
                       .prefetch_related('backup_expiration', 'user'):
            self.accumulate(self.do_stage(v, v.backup_expiration, v.user))
        return self.counts

    def do_expire(self, volume):
        return delete_backup_worker(volume)

    def add_target_details(self, volume, context):
        pass


class InstanceExpirer(Expirer):
    '''This expirer shelves instances
    '''

    def __init__(self, **kwargs):
        super().__init__('email/instance_expiry.html',
                         first_warning=days(settings.INSTANCE_WARNING_1),
                         final_warning=days(settings.INSTANCE_WARNING_2),
                         **kwargs)

    def run(self, feature):
        for i in Instance.objects.exclude(expiration=None) \
                                 .filter(deleted=None,
                                         marked_for_deletion=None) \
                                 .prefetch_related('expiration', 'user'):
            self.accumulate(self.do_stage(i, i.expiration, i.user))
        return self.counts

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
        for r in Resize.objects.exclude(expiration=None) \
                               .filter(reverted=None,
                                       instance__marked_for_deletion=None,
                                       instance__deleted=None) \
                               .prefetch_related('expiration', 'instance'):
            self.accumulate(self.do_stage(r, r.expiration, r.instance.user))
        return self.counts

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
