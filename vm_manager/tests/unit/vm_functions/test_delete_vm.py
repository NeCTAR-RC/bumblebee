import copy
from datetime import datetime, timedelta, timezone
import uuid

import novaclient

from unittest.mock import Mock, patch, call

from django.conf import settings
from django.test import TestCase

from researcher_desktop.utils.utils import get_desktop_type, desktops_feature
from guacamole.tests.factories import GuacamoleConnectionFactory
from vm_manager.tests.common import UUID_1, UUID_2, UUID_3, UUID_4
from vm_manager.tests.fakes import Fake, FakeServer, FakeVolume, FakeNectar
from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase

from vm_manager.constants import VM_MISSING, VM_OKAY, VM_SHELVED, NO_VM, \
    INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME, \
    INSTANCE_CHECK_SHUTOFF_RETRY_COUNT, INSTANCE_DELETION_RETRY_COUNT
from guacamole.models import GuacamoleConnection
from vm_manager.models import VMStatus, Volume, Instance
from vm_manager.vm_functions.delete_vm import delete_vm_worker, \
    _check_instance_is_shutoff_and_delete, \
    _delete_volume_once_instance_is_deleted
from vm_manager.utils.utils import get_nectar


class DeleteVMTests(VMFunctionTestBase):

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.vm_functions.delete_vm.django_rq')
    @patch('vm_manager.vm_functions.delete_vm.logger')
    def test_delete_vm_worker(self, mock_logger, mock_rq):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        _, fake_instance = self.build_fake_vol_instance(ip_address='10.0.0.99')

        fake_guac = GuacamoleConnectionFactory.create(instance=fake_instance)
        fake_instance.guac_connection = fake_guac

        fake_nectar = get_nectar()
        fake_nectar.nova.servers.stop.side_effect = \
            novaclient.exceptions.NotFound(code=42)  # the code is ignored

        result = delete_vm_worker(fake_instance)

        self.assertIsNone(result)
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNone(instance.guac_connection)
        self.assertEqual(
            0,
            GuacamoleConnection.objects.filter(instance=instance).count())
        fake_nectar.nova.servers.stop.assert_called_once_with(fake_instance.id)
        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
            _check_instance_is_shutoff_and_delete,
            fake_instance,
            INSTANCE_CHECK_SHUTOFF_RETRY_COUNT,
            _delete_volume_once_instance_is_deleted,
            (fake_instance, INSTANCE_DELETION_RETRY_COUNT))

        mock_logger.error.assert_called_once_with(
            f"Trying to delete an instance that's missing "
            f"from OpenStack {fake_instance}")
        mock_logger.info.assert_has_calls([
            call(f"About to delete vm at addr: 10.0.0.99 "
                 f"for user {self.user.username}"),
            call(f"Checking whether {fake_instance} is ShutOff "
                 f"after {INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME} "
                 f"seconds and Delete it")
            ])
