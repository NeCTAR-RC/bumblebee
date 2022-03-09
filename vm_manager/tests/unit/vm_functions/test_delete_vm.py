from datetime import timedelta

import novaclient

from unittest.mock import Mock, patch, call


from guacamole.tests.factories import GuacamoleConnectionFactory
from vm_manager.tests.fakes import Fake, FakeServer, FakeNectar
from vm_manager.tests.unit.vm_functions.base import VMFunctionTestBase

from vm_manager.constants import ACTIVE, SHUTDOWN, VM_WAITING, \
    INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME, \
    INSTANCE_DELETION_RETRY_WAIT_TIME, \
    INSTANCE_CHECK_SHUTOFF_RETRY_COUNT, INSTANCE_DELETION_RETRY_COUNT
from guacamole.models import GuacamoleConnection
from vm_manager.models import VMStatus, Volume, Instance
from vm_manager.vm_functions.delete_vm import delete_vm_worker, \
    _check_instance_is_shutoff_and_delete, _delete_instance_worker, \
    _delete_volume_once_instance_is_deleted, delete_volume
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

    @patch('vm_manager.models.get_nectar')
    @patch('vm_manager.vm_functions.delete_vm.django_rq')
    @patch('vm_manager.vm_functions.delete_vm.logger')
    def test_check_instance_shutoff(self, mock_logger, mock_rq,
                                    mock_get_nectar):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        _, fake_instance = self.build_fake_vol_instance(ip_address='10.0.0.99')
        funky = Fake()
        funky_args = (1, 2)

        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get.return_value = FakeServer(status=ACTIVE)

        _check_instance_is_shutoff_and_delete(
            fake_instance, 1, funky, funky_args)

        mock_logger.info.assert_called_with(
            f"{fake_instance} is not shutoff yet! Will check again in "
            f"{INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME} seconds")
        mock_rq.get_scheduler.assert_called_once_with("default")
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=INSTANCE_CHECK_SHUTOFF_RETRY_WAIT_TIME),
            _check_instance_is_shutoff_and_delete, fake_instance,
            0, funky, funky_args)

    @patch('vm_manager.models.get_nectar')
    @patch('vm_manager.vm_functions.delete_vm.django_rq')
    @patch('vm_manager.vm_functions.delete_vm.logger')
    @patch('vm_manager.vm_functions.delete_vm._delete_instance_worker')
    def test_check_instance_shutoff_2(self, mock_worker, mock_logger,
                                      mock_rq, mock_get_nectar):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler
        _, fake_instance, fake_status = self.build_fake_vol_inst_status(
            ip_address='10.0.0.99', status=VM_WAITING)
        funky = Fake()
        funky_args = (1, 2)

        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get.return_value = FakeServer(status=ACTIVE)

        _check_instance_is_shutoff_and_delete(
            fake_instance, 0, funky, funky_args)

        mock_rq.get_scheduler.assert_called_once_with("default")
        mock_logger.info.assert_called_with(
            f"Ran out of retries. {fake_instance} shutoff took too long."
            f"Proceeding to delete Openstack instance anyway!")
        mock_worker.assert_called_once_with(fake_instance)
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
            funky, *funky_args)
        updated_status = VMStatus.objects.get(pk=fake_status.pk)
        self.assertEqual(66, updated_status.status_progress)
        self.assertIsNotNone(updated_status.status_message)

    @patch('vm_manager.vm_functions.delete_vm.get_nectar')
    @patch('vm_manager.vm_functions.delete_vm.logger')
    def test_delete_instance_worker(self, mock_logger, mock_get_nectar):
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar

        _, fake_instance = self.build_fake_vol_instance(ip_address='10.0.0.99')

        self.assertIsNone(_delete_instance_worker(fake_instance))
        fake_nectar.nova.servers.delete.assert_called_once_with(
            fake_instance.id)
        mock_logger.info.assert_called_once_with(
            f"Instructed OpenStack to delete {fake_instance}")

    @patch('vm_manager.vm_functions.delete_vm.get_nectar')
    @patch('vm_manager.vm_functions.delete_vm.logger')
    def test_delete_instance_worker_2(self, mock_logger, mock_get_nectar):
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.delete.side_effect = \
            novaclient.exceptions.NotFound(code=42)  # code is not used

        _, fake_instance = self.build_fake_vol_instance(ip_address='10.0.0.99')

        self.assertIsNone(_delete_instance_worker(fake_instance))
        fake_nectar.nova.servers.delete.assert_called_once_with(
            fake_instance.id)
        mock_logger.info.assert_called_once_with(
            f"Instance {fake_instance} already deleted")

    @patch('vm_manager.vm_functions.delete_vm.get_nectar')
    @patch('vm_manager.vm_functions.delete_vm.logger')
    def test_delete_instance_worker_3(self, mock_logger, mock_get_nectar):
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.delete.side_effect = Exception("weirdness")

        _, fake_instance = self.build_fake_vol_instance(ip_address='10.0.0.99')

        self.assertIsNone(_delete_instance_worker(fake_instance))
        fake_nectar.nova.servers.delete.assert_called_once_with(
            fake_instance.id)
        mock_logger.info.assert_not_called()
        mock_logger.error.assert_called_once_with(
            f"something went wrong with the instance deletion "
            f"call for {fake_instance}, it raised weirdness")

    @patch('vm_manager.vm_functions.delete_vm.get_nectar')
    @patch('vm_manager.vm_functions.delete_vm.logger')
    @patch('vm_manager.vm_functions.delete_vm.delete_volume')
    def test_delete_volume_once_instance_is_deleted(
            self, mock_delete, mock_logger, mock_get_nectar):
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get.side_effect = \
            novaclient.exceptions.NotFound(code=42)  # code is ignored

        fake_volume, fake_instance = self.build_fake_vol_instance(
            ip_address='10.0.0.99')
        self.assertIsNone(fake_instance.deleted)

        self.assertIsNone(
            _delete_volume_once_instance_is_deleted(fake_instance, 1))
        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)
        mock_delete.assert_called_once_with(fake_volume)
        mock_logger.info.assert_called_once_with(
            f"Instance {fake_instance.id} successfully deleted, "
            f"we can delete the volume now!")
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNotNone(instance.deleted)

    @patch('vm_manager.vm_functions.delete_vm.get_nectar')
    @patch('vm_manager.vm_functions.delete_vm.logger')
    @patch('vm_manager.vm_functions.delete_vm.delete_volume')
    def test_delete_volume_once_instance_is_deleted_2(
            self, mock_delete, mock_logger, mock_get_nectar):
        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get.side_effect = Exception("wonderfulness")

        fake_volume, fake_instance = self.build_fake_vol_instance(
            ip_address='10.0.0.99')
        self.assertIsNone(fake_instance.deleted)

        self.assertIsNone(
            _delete_volume_once_instance_is_deleted(fake_instance, 1))
        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)
        mock_delete.assert_not_called()
        mock_logger.error.assert_called_once_with(
            f"something went wrong with the instance get "
            f"call for {fake_instance}, it raised wonderfulness")
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertIsNone(instance.deleted)

    @patch('vm_manager.vm_functions.delete_vm.get_nectar')
    @patch('vm_manager.vm_functions.delete_vm.django_rq')
    @patch('vm_manager.vm_functions.delete_vm.logger')
    @patch('vm_manager.vm_functions.delete_vm.delete_volume')
    @patch('vm_manager.vm_functions.delete_vm._delete_instance_worker')
    def test_delete_volume_once_instance_is_deleted_3(
            self, mock_delete_instance, mock_delete_volume,
            mock_logger, mock_rq, mock_get_nectar):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler

        fake_volume, fake_instance = self.build_fake_vol_instance(
            ip_address='10.0.0.99')

        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=SHUTDOWN)

        self.assertIsNone(
            _delete_volume_once_instance_is_deleted(fake_instance, 0))
        mock_logger.info.assert_not_called()
        mock_logger.error.assert_not_called()

        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)
        mock_delete_volume.assert_not_called()
        mock_delete_instance.assert_called_once_with(fake_instance)
        mock_rq.get_scheduler.assert_called_once_with("default")
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(minutes=INSTANCE_DELETION_RETRY_WAIT_TIME),
            _delete_volume_once_instance_is_deleted, fake_instance,
            -1)

    @patch('vm_manager.vm_functions.delete_vm.get_nectar')
    @patch('vm_manager.vm_functions.delete_vm.django_rq')
    @patch('vm_manager.vm_functions.delete_vm.logger')
    @patch('vm_manager.vm_functions.delete_vm.delete_volume')
    @patch('vm_manager.vm_functions.delete_vm._delete_instance_worker')
    def test_delete_volume_once_instance_is_deleted_4(
            self, mock_delete_instance, mock_delete_volume,
            mock_logger, mock_rq, mock_get_nectar):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler

        fake_volume, fake_instance = self.build_fake_vol_instance(
            ip_address='10.0.0.99')

        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=SHUTDOWN)

        self.assertIsNone(
            _delete_volume_once_instance_is_deleted(fake_instance, -1))
        mock_logger.info.assert_not_called()
        message = "ran out of retries trying to delete"
        mock_logger.error.assert_called_once_with(f"{message} {fake_instance}")

        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)
        mock_delete_volume.assert_not_called()
        mock_delete_instance.assert_not_called()
        mock_rq.get_scheduler.assert_not_called()
        mock_scheduler.enqueue_in.assert_not_called()
        instance = Instance.objects.get(pk=fake_instance.pk)
        self.assertEqual(message, instance.error_message)
        self.assertEqual(message, instance.boot_volume.error_message)

    @patch('vm_manager.vm_functions.delete_vm.get_nectar')
    @patch('vm_manager.vm_functions.delete_vm.django_rq')
    @patch('vm_manager.vm_functions.delete_vm.logger')
    @patch('vm_manager.vm_functions.delete_vm.delete_volume')
    @patch('vm_manager.vm_functions.delete_vm._delete_instance_worker')
    def test_delete_volume_once_instance_is_deleted_5(
            self, mock_delete_instance, mock_delete_volume,
            mock_logger, mock_rq, mock_get_nectar):
        mock_scheduler = Mock()
        mock_rq.get_scheduler.return_value = mock_scheduler

        fake_volume, fake_instance = self.build_fake_vol_instance(
            ip_address='10.0.0.99')

        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.nova.servers.get.return_value = FakeServer(
            id=fake_instance.id, status=SHUTDOWN)

        self.assertIsNone(
            _delete_volume_once_instance_is_deleted(fake_instance, 1))
        mock_logger.info.assert_not_called()
        mock_logger.error.assert_not_called()

        fake_nectar.nova.servers.get.assert_called_once_with(fake_instance.id)
        mock_delete_volume.assert_not_called()
        mock_delete_instance.assert_called_once_with(fake_instance)
        mock_rq.get_scheduler.assert_called_once_with('default')
        mock_scheduler.enqueue_in.assert_called_once_with(
            timedelta(seconds=INSTANCE_DELETION_RETRY_WAIT_TIME),
            _delete_volume_once_instance_is_deleted, fake_instance, 0)

    @patch('vm_manager.vm_functions.delete_vm.get_nectar')
    def test_delete_volume(self, mock_get_nectar):

        fake_volume = self.build_fake_volume()

        fake_nectar = FakeNectar()
        mock_get_nectar.return_value = fake_nectar
        fake_nectar.cinder.volumes.return_value = 99

        self.assertIsNone(delete_volume(fake_volume))
        mock_get_nectar.assert_called_once()
        fake_nectar.cinder.volumes.delete.assert_called_once_with(
            fake_volume.id)
        volume = Volume.objects.get(pk=fake_volume.pk)
        self.assertIsNotNone(volume.deleted)
