from datetime import datetime, timedelta
import re
from unittest.mock import Mock, patch
import uuid

from django.test import TestCase
from django.utils.timezone import utc

from researcher_desktop.utils.utils import get_desktop_type, desktops_feature

from vm_manager.models import Expiration
from vm_manager.utils.expirer import Expirer, \
    EXP_INITIAL, EXP_FIRST_WARNING, EXP_FINAL_WARNING, EXP_EXPIRING, \
    EXP_EXPIRY_COMPLETED, EXP_EXPIRY_FAILED, EXP_EXPIRY_FAILED_RETRYABLE, \
    EXP_NOTIFY, EXP_SUCCESS, EXP_FAIL, EXP_RETRY, EXP_SKIP, EXP_STARTED

from researcher_workspace.tests.factories import UserFactory


class DummyExpirer(Expirer):
    def __init__(self, res=EXP_SUCCESS, **kwargs):
        super().__init__('email/test_expiry.html', **kwargs)
        self.do_expire = Mock()
        self.do_expire.return_value = res
        self.add_target_details = Mock()

    def run(self, resource, expiration, user):
        return self.do_stage(resource, expiration, user)


class ExpirerTests(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.FEATURE = desktops_feature()
        self.UBUNTU = get_desktop_type('ubuntu')
        self.user = UserFactory.create()

    def build_instance(self, expires=None):
        fake_volume = VolumeFactory.create(
            id=uuid.uuid4(),
            user=self.user,
            image=uuid.uuid4(),
            operating_system=self.UBUNTU.id,
            requesting_feature=self.UBUNTU.feature,
            zone="a_zone",
            flavor=uuid.uuid4())
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(),
            boot_volume=fake_volume,
            user=self.user,
            expires=expires)
        return fake_instance

    @patch('vm_manager.utils.expirer.send_notification')
    @patch('builtins.print')
    def test_notify(self, mock_print, mock_send):
        expirer = DummyExpirer(dry_run=False)
        context = {'one': 1}
        expirer.notify(self.user, context)
        mock_send.assert_called_once_with(
            self.user, 'email/test_expiry.html', context)

        expirer = DummyExpirer(dry_run=True, verbose=True)
        expirer.notify(self.user, context)

        calls = mock_print.mock_calls
        self.assertEqual(1, len(calls))
        _, args, kwargs = calls[0]
        self.assertEqual(1, len(args))
        self.assertRegex(args[0], re.escape(self.user.get_full_name()))
        self.assertRegex(args[0], re.escape(self.user.email))
        self.assertRegex(args[0], "One is 1")
        self.assertEqual({}, kwargs)

    def test_accumulate(self):
        expirer = DummyExpirer()
        expirer.accumulate("fee")
        expirer.accumulate("fee")
        expirer.accumulate("fi")
        self.assertEqual({'fee': 2, 'fi': 1}, expirer.counts)

    def test_do_expire_first_time(self):
        '''
        Tests simulating first attempt at expiring
        '''

        now = datetime.now(utc)
        target = object()

        # When do_expire returns EXP_SUCCESS ...
        fake_expiration = Expiration(expires=now - timedelta(days=1),
                                     stage=EXP_FINAL_WARNING,
                                     stage_date=now - timedelta(days=2))
        fake_expiration.save()
        expirer = DummyExpirer(final_warning=timedelta(days=1))
        self.assertEqual(EXP_SUCCESS,
                         expirer.do_stage(target, fake_expiration, self.user))
        expiration = Expiration.objects.get(pk=fake_expiration.pk)
        self.assertEqual(EXP_EXPIRY_COMPLETED, expiration.stage)
        expirer.do_expire.assert_called_once_with(target)

        # When do_expire returns EXP_FAIL ...
        fake_expiration = Expiration(expires=now - timedelta(days=1),
                                     stage=EXP_FINAL_WARNING,
                                     stage_date=now - timedelta(days=2))
        fake_expiration.save()
        expirer = DummyExpirer(res=EXP_FAIL, final_warning=timedelta(days=1))
        self.assertEqual(EXP_FAIL,
                         expirer.do_stage(target, fake_expiration, self.user))
        expiration = Expiration.objects.get(pk=fake_expiration.pk)
        self.assertEqual(EXP_EXPIRY_FAILED, expiration.stage)
        expirer.do_expire.assert_called_once_with(target)

        # When do_expire returns EXP_STARTED ...
        fake_expiration = Expiration(expires=now - timedelta(days=1),
                                     stage=EXP_FINAL_WARNING,
                                     stage_date=now - timedelta(days=2))
        fake_expiration.save()
        expirer = DummyExpirer(res=EXP_STARTED,
                               final_warning=timedelta(days=1))
        self.assertEqual(EXP_STARTED,
                         expirer.do_stage(target, fake_expiration, self.user))
        expiration = Expiration.objects.get(pk=fake_expiration.pk)
        self.assertEqual(EXP_EXPIRING, expiration.stage)
        expirer.do_expire.assert_called_once_with(target)

        # When do_expire returns EXP_RETRY ...
        fake_expiration = Expiration(expires=now - timedelta(days=1),
                                     stage=EXP_FINAL_WARNING,
                                     stage_date=now - timedelta(days=2))
        fake_expiration.save()
        expirer = DummyExpirer(res=EXP_RETRY,
                               final_warning=timedelta(days=1))
        self.assertEqual(EXP_RETRY,
                         expirer.do_stage(target, fake_expiration, self.user))
        expiration = Expiration.objects.get(pk=fake_expiration.pk)
        self.assertEqual(EXP_EXPIRY_FAILED_RETRYABLE, expiration.stage)
        expirer.do_expire.assert_called_once_with(target)

        # When do_expire returns EXP_SKIP ...
        fake_expiration = Expiration(expires=now - timedelta(days=1),
                                     stage=EXP_FINAL_WARNING,
                                     stage_date=now - timedelta(days=2))
        fake_expiration.save()
        expirer = DummyExpirer(res=EXP_SKIP,
                               final_warning=timedelta(days=1))
        self.assertEqual(EXP_SKIP,
                         expirer.do_stage(target, fake_expiration, self.user))
        expiration = Expiration.objects.get(pk=fake_expiration.pk)
        self.assertEqual(EXP_FINAL_WARNING, expiration.stage)
        expirer.do_expire.assert_called_once_with(target)

    def test_do_expire_retry(self):
        '''
        Test simulating a retry
        '''

        now = datetime.now(utc)
        target = object()

        fake_expiration = Expiration(expires=now - timedelta(days=1),
                                     stage=EXP_EXPIRY_FAILED_RETRYABLE,
                                     stage_date=now - timedelta(days=2))
        fake_expiration.save()
        expirer = DummyExpirer(final_warning=timedelta(days=1))
        self.assertEqual(EXP_SUCCESS,
                         expirer.do_stage(target, fake_expiration, self.user))
        expiration = Expiration.objects.get(pk=fake_expiration.pk)
        self.assertEqual(EXP_EXPIRY_COMPLETED, expiration.stage)
        expirer.do_expire.assert_called_once_with(target)

    @patch("vm_manager.utils.expirer.logger")
    def test_do_expire_long_running(self, mock_logger):
        '''
        Test simulating a long running expiry action
        '''

        now = datetime.now(utc)
        target = object()

        fake_expiration = Expiration(expires=now - timedelta(days=1),
                                     stage=EXP_EXPIRING,
                                     stage_date=now - timedelta(days=2))
        fake_expiration.save()
        expirer = DummyExpirer(final_warning=timedelta(days=1))
        self.assertEqual(EXP_SKIP,
                         expirer.do_stage(target, fake_expiration, self.user))
        expiration = Expiration.objects.get(pk=fake_expiration.pk)
        self.assertEqual(EXP_EXPIRING, expiration.stage)
        expirer.do_expire.assert_not_called()
        mock_logger.warning.assert_called_once_with(
            f"Expiration already running for {fake_expiration}: skip")

    @patch("vm_manager.utils.expirer.logger")
    def test_do_expire_wrong_state(self, mock_logger):
        '''
        Test calls to do_stage in the wrong state
        '''

        now = datetime.now(utc)
        target = object()

        fake_expiration = Expiration(expires=now - timedelta(days=1),
                                     stage=EXP_EXPIRY_COMPLETED,
                                     stage_date=now - timedelta(days=2))
        fake_expiration.save()
        expirer = DummyExpirer(final_warning=timedelta(days=1))
        self.assertEqual(EXP_SKIP,
                         expirer.do_stage(target, fake_expiration, self.user))
        expiration = Expiration.objects.get(pk=fake_expiration.pk)
        self.assertEqual(EXP_EXPIRY_COMPLETED, expiration.stage)
        expirer.do_expire.assert_not_called()
        mock_logger.error.assert_called_once_with(
            "Expiration stage wrong: "
            f"{expirer}, {target}, {fake_expiration}, {self.user}: skip")

        mock_logger.error.reset_mock()

        fake_expiration = Expiration(expires=now - timedelta(days=1),
                                     stage=EXP_EXPIRY_FAILED,
                                     stage_date=now - timedelta(days=2))
        fake_expiration.save()
        expirer = DummyExpirer(final_warning=timedelta(days=1))
        self.assertEqual(EXP_SKIP,
                         expirer.do_stage(target, fake_expiration, self.user))
        expiration = Expiration.objects.get(pk=fake_expiration.pk)
        self.assertEqual(EXP_EXPIRY_FAILED, expiration.stage)
        expirer.do_expire.assert_not_called()
        mock_logger.error.assert_called_once_with(
            "Expiration stage wrong: "
            f"{expirer}, {target}, {fake_expiration}, {self.user}: skip")

    def test_stages_1(self):
        '''
        Test the staging behavior of an expirer with final warning only.
        Caveat: we simulate the behavior of running the expirer running
        once a day at a precise time.  In practice they will be run more
        frequently, and the interval between runs won't be a precise value.
        '''

        now = datetime.now(utc)
        expiration = Expiration(expires=now + timedelta(days=7),
                                stage=EXP_INITIAL, stage_date=now)
        expiration.save()
        now = now + timedelta(seconds=1)
        expirer = DummyExpirer(dry_run=False,
                               final_warning=timedelta(days=1))
        expirer.notify = Mock()
        target = object()

        stage = EXP_INITIAL
        # The i values are simulated days into the future
        for i in range(0, 9):
            old_stage_date = expiration.stage_date
            # Time warping the expirer.
            expirer.now = now + timedelta(days=i)

            res = expirer.do_stage(target, expiration, self.user)
            self.assertEqual(EXP_SUCCESS if i == 7
                             else EXP_NOTIFY if i == 6
                             else EXP_SKIP,
                             res)
            if i in (6, 7):
                # The 'first warning' stage should be skipped.
                next_stage = (EXP_FINAL_WARNING if stage == EXP_INITIAL
                              else EXP_EXPIRY_COMPLETED)
                self.assertEqual(next_stage, expiration.stage)
                stage = next_stage
                if i == 7:
                    expirer.notify.assert_not_called()
                    expirer.do_expire.assert_called_once_with(target)
                    expirer.do_expire.reset_mock()
                else:
                    expirer.notify.assert_called_once()
                    _, args, kwargs = expirer.notify.mock_calls[0]
                    self.assertEqual(2, len(args))
                    self.assertEqual(self.user, args[0])
                    self.assertEqual('final', args[1]['warning'])
                    self.assertEqual({}, kwargs)
                    expirer.notify.reset_mock()
                    expirer.add_target_details.assert_called_once()
                    expirer.add_target_details.reset_mock()
                    expirer.do_expire.assert_not_called()
                updated = Expiration.objects.get(pk=expiration.pk)
                self.assertEqual(stage, updated.stage)
                self.assertEqual(expirer.now, updated.stage_date)
            else:
                self.assertEqual(stage, expiration.stage)
                expirer.notify.assert_not_called()
                expirer.do_expire.assert_not_called()
                updated = Expiration.objects.get(pk=expiration.pk)
                self.assertEqual(stage, updated.stage)
                self.assertEqual(old_stage_date, updated.stage_date)

    def test_stages_2(self):
        '''
        Test the staging behavior of an expirer with first and final
        warnings.
        '''

        now = datetime.now(utc)
        expiration = Expiration(expires=now + timedelta(days=14),
                                stage=EXP_INITIAL, stage_date=now)
        now = now + timedelta(seconds=1)
        expirer = DummyExpirer(dry_run=False,
                               first_warning=timedelta(days=7),
                               final_warning=timedelta(days=1))
        expirer.notify = Mock()
        target = object()

        stage = EXP_INITIAL
        for i in range(0, 15):
            # Time warping the expirer
            expirer.now = now + timedelta(days=i)

            res = expirer.do_stage(target, expiration, self.user)
            self.assertEqual(EXP_SUCCESS if i == 14
                             else EXP_NOTIFY if i in (7, 13)
                             else EXP_SKIP,
                             res)
            if i in (7, 13, 14):
                next_stage = (
                    EXP_FIRST_WARNING if stage == EXP_INITIAL
                    else EXP_FINAL_WARNING if stage == EXP_FIRST_WARNING
                    else EXP_EXPIRY_COMPLETED)
                self.assertEqual(next_stage, expiration.stage)
                stage = next_stage
                if i == 14:
                    expirer.notify.assert_not_called()
                    expirer.do_expire.assert_called_once_with(target)
                    expirer.do_expire.reset_mock()
                else:
                    expirer.notify.assert_called_once()
                    _, args, kwargs = expirer.notify.mock_calls[0]
                    self.assertEqual(2, len(args))
                    self.assertEqual(self.user, args[0])
                    self.assertEqual('first' if stage == EXP_FIRST_WARNING
                                     else 'final',
                                     args[1]['warning'])
                    self.assertEqual({}, kwargs)
                    expirer.notify.reset_mock()
                    expirer.add_target_details.assert_called_once()
                    expirer.add_target_details.reset_mock()
                    expirer.do_expire.assert_not_called()
            else:
                self.assertEqual(stage, expiration.stage)
                expirer.notify.assert_not_called()
                expirer.do_expire.assert_not_called()
