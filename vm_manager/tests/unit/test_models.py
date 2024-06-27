from datetime import datetime, timezone
from unittest.mock import patch
import uuid

from django.http import Http404
from django.test import TestCase

from researcher_workspace.tests.factories import FeatureFactory, UserFactory
from researcher_desktop.tests.factories import DesktopTypeFactory
from guacamole.models import GuacamoleEntity, GuacamoleConnectionParameter, \
    GuacamoleConnectionPermission
from guacamole.tests.factories import GuacamoleConnectionFactory
from vm_manager.tests.factories import InstanceFactory, VolumeFactory, \
    ResizeFactory, VMStatusFactory
from vm_manager.tests.fakes import Fake, FakeNectar
from vm_manager.constants import ERROR
from vm_manager.utils.utils import get_nectar

from vm_manager.models import Instance, Volume, Resize, VMStatus, \
    _create_hostname_id

utc = timezone.utc


class VMManagerModelTestBase(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.user = UserFactory.create()
        self.feature = FeatureFactory.create(app_name='feature')
        self.desktop_type = DesktopTypeFactory.create(
            id='desktop', name='desktop', feature=self.feature)

    def do_superclass_method_tests(self, resource):
        self.assertIsNone(resource.error_flag)
        self.assertIsNone(resource.error_message)
        now = datetime.now(utc)
        resource.error("Bad troubles")
        self.assertEqual("Bad troubles", resource.error_message)
        self.assertTrue(now <= resource.error_flag)

        self.assertIsNone(resource.marked_for_deletion)
        resource.set_marked_for_deletion()
        self.assertTrue(now <= resource.marked_for_deletion)

    def make_volume(self, **kwargs):
        my_kwargs = {
            'id': uuid.uuid4(),
            'user': self.user,
            'operating_system': self.desktop_type.id,
            'requesting_feature': self.desktop_type.feature,
            'zone': 'QRIScloud',
        }
        my_kwargs.update(kwargs)
        return VolumeFactory.create(**my_kwargs)


class VolumeModelTests(VMManagerModelTestBase):

    def test_superclass_methods(self):
        fake_volume = self.make_volume()
        self.do_superclass_method_tests(fake_volume)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    @patch('vm_manager.models._create_hostname_id')
    def test_volume_save(self, mock_gen):
        mock_gen.return_value = "fnord"
        id = uuid.uuid4()
        volume = self.make_volume(id=id)
        self.assertEqual("fnord", volume.hostname_id)
        mock_gen.assert_called_once()

        mock_gen.return_value = ERROR
        id = uuid.uuid4()
        with self.assertRaises(ValueError) as cm:
            volume = self.make_volume(id=id)
        self.assertEqual("Could not assign random value to volume",
                         str(cm.exception))
        fake = get_nectar()
        fake.cinder.volumes.delete.assert_called_once_with(id)

    @patch('vm_manager.models.nanoid')
    def test_create_hostname_id(self, mock_nanoid):
        mock_nanoid.generate.return_value = "xxxxxx"
        self.make_volume()
        mock_nanoid.generate.assert_called_once()

        self.assertEqual(ERROR, _create_hostname_id())

        self.assertEqual(101, mock_nanoid.generate.call_count)

    def test_get_volume(self):
        self.assertIsNone(Volume.objects.get_volume(self.user,
                                                    self.desktop_type))
        volume = self.make_volume()
        self.assertEqual(volume,
                         Volume.objects.get_volume(self.user,
                                                   self.desktop_type))
        volume = self.make_volume()
        with self.assertRaises(Volume.MultipleObjectsReturned) as cm:
            Volume.objects.get_volume(self.user, self.desktop_type)
        self.assertEqual(
            "Multiple current volumes found in the database with "
            f"user={self.user} and os={self.desktop_type.id}",
            str(cm.exception))

    def test_set_expires(self):
        volume = self.make_volume()
        self.assertIsNone(volume.expiration)

        now = datetime.now(utc)
        volume.set_expires(now)
        self.assertIsNotNone(volume.expiration)
        self.assertEqual(now, volume.expiration.expires)
        self.assertEqual(0, volume.expiration.stage)
        self.assertIsNotNone(volume.expiration.stage_date)

        now = datetime.now(utc)
        volume.set_expires(now)
        self.assertIsNotNone(volume.expiration)
        self.assertEqual(now, volume.expiration.expires)
        self.assertEqual(0, volume.expiration.stage)
        self.assertIsNotNone(volume.expiration.stage_date)

        volume.set_expires(None)
        self.assertIsNone(volume.expiration)


class InstanceModelTests(VMManagerModelTestBase):

    def test_superclass_methods(self):
        fake_volume = self.make_volume()
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        self.do_superclass_method_tests(fake_instance)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    def test_get_ip_addr(self):
        fake_volume = self.make_volume()
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        self.assertIsNone(fake_instance.ip_address)

        fake = get_nectar()
        fake.nova.servers.get.reset_mock()
        dummy_ip = "192.168.1.30"
        fake.nova.servers.get.return_value = Fake(
            addresses={
                'private': [
                    {
                        "OS-EXT-IPS-MAC:mac_addr": "00:0c:29:0d:11:74",
                        "OS-EXT-IPS:type": "fixed",
                        "addr": dummy_ip,
                        "version": 4
                    }
                ]
            }
        )

        ip = fake_instance.get_ip_addr()

        fake.nova.servers.get.assert_called_once_with(fake_instance.id)
        self.assertEqual(dummy_ip, ip)
        self.assertIsNotNone(fake_instance.ip_address)

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    def test_get_status(self):
        fake = get_nectar()
        fake.nova.servers.get.return_value = Fake(status='testing')
        fake.nova.servers.get.reset_mock()

        fake_volume = self.make_volume()
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        status = fake_instance.get_status()

        fake.nova.servers.get.assert_called_once_with(fake_instance.id)
        self.assertEqual('testing', status)

    def test_create_guac_connection(self):
        fake_volume = self.make_volume()
        fake_guac_connection = GuacamoleConnectionFactory.create()
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume,
            guac_connection=fake_guac_connection,
            ip_address="10.0.0.1")

        GuacamoleEntity.objects.create(
            name=self.user.username, type='USER')

        self.assertEqual(0,
                         GuacamoleConnectionParameter.objects.filter(
                             connection=fake_guac_connection).count())

        fake_instance.create_guac_connection()

        entity = GuacamoleEntity.objects.get(name=self.user.username)
        self.assertIsNotNone(entity)
        self.assertEqual(11,
                         GuacamoleConnectionParameter.objects.filter(
                             connection=fake_guac_connection).count())
        self.assertEqual(1,
                         GuacamoleConnectionPermission.objects.filter(
                             connection=fake_guac_connection,
                             entity=entity, permission='READ').count())

        # This is what create_guac_connection is used for ...
        url = fake_instance.get_url()
        self.assertTrue(
            url.startswith("https://tiger-guacamole-qriscloud.example.com"
                           "/#/client/"))

    def test_get_instance(self):
        self.assertIsNone(
            Instance.objects.get_instance(self.user, self.desktop_type))

        fake_volume = self.make_volume()
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        self.assertEqual(
            fake_instance,
            Instance.objects.get_instance(self.user, self.desktop_type))

        # This is badness for testing
        InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        with self.assertRaises(Instance.MultipleObjectsReturned) as cm:
            Instance.objects.get_instance(self.user, self.desktop_type)
        self.assertEqual("Multiple current instances found in the database "
                         f"with user={self.user} and "
                         f"os={self.desktop_type.name}",
                         str(cm.exception))

    def test_get_instance_by_ip(self):
        ip_address = '10.0.0.2'
        self.assertIsNone(
            Instance.objects.get_instance_by_ip_address(
                ip_address, self.desktop_type.feature))

        fake_volume = self.make_volume()
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume,
            ip_address=ip_address)

        self.assertEqual(
            fake_instance,
            Instance.objects.get_instance_by_ip_address(
                ip_address, self.desktop_type.feature))

        # This is badness for testing
        InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume,
            ip_address=ip_address)

        with self.assertRaises(Instance.MultipleObjectsReturned) as cm:
            Instance.objects.get_instance_by_ip_address(
                ip_address, self.desktop_type.feature)
        self.assertEqual("Multiple current instances found in the database "
                         f"with ip_address={ip_address}",
                         str(cm.exception))

    @patch('vm_manager.utils.utils.Nectar', new=FakeNectar)
    def test_get_instance_by_ip_with_lookup(self):
        ip_address = '10.0.0.3'
        ip_address_2 = '10.0.0.4'

        fake_volume = self.make_volume()
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        fake = get_nectar()
        fake.nova.servers.get.reset_mock()
        fake.nova.servers.get.return_value = Fake(
            addresses={
                'private': [
                    {
                        "OS-EXT-IPS-MAC:mac_addr": "00:0c:29:0d:11:74",
                        "OS-EXT-IPS:type": "fixed",
                        "addr": ip_address,
                        "version": 4
                    }
                ]
            }
        )

        self.assertIsNone(
            Instance.objects.get_instance_by_ip_address(
                ip_address_2, self.desktop_type.feature))
        fake.nova.servers.get.assert_called_once_with(fake_instance.id)

        fake_instance_2 = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        fake.nova.servers.get.return_value = Fake(
            addresses={
                'private': [
                    {
                        "OS-EXT-IPS-MAC:mac_addr": "00:0c:29:0d:11:74",
                        "OS-EXT-IPS:type": "fixed",
                        "addr": ip_address_2,
                        "version": 4
                    }
                ]
            }
        )

        self.assertEqual(
            fake_instance_2,
            Instance.objects.get_instance_by_ip_address(
                ip_address_2, self.desktop_type.feature))

        test_instance = Instance.objects.get(pk=fake_instance_2.pk)
        self.assertEqual(test_instance.ip_address, ip_address_2)

    @patch('vm_manager.models.logger')
    def test_get_instance_by_vm_id(self, mock_logger):

        # Don't know how to trigger the `ValueError` case.

        with self.assertRaises(Http404):
            Instance.objects.get_instance_by_untrusted_vm_id(
                None, self.user, self.feature)
        mock_logger.error.assert_called_with(
            "Trying to get a vm that doesn't exist with "
            f"vm_id: None, called by {self.user}")

        with self.assertRaises(Http404):
            Instance.objects.get_instance_by_untrusted_vm_id(
                'fnoord', self.user, self.feature)
        mock_logger.error.assert_called_with(
            "Validation error (['“fnoord” is not a valid UUID.']) trying "
            f"to get a VM with vm_id: fnoord, called by {self.user}")

        id = uuid.uuid4()
        with self.assertRaises(Http404):
            Instance.objects.get_instance_by_untrusted_vm_id(
                id, self.user, self.feature)
        mock_logger.error.assert_called_with(
            "Trying to get a vm that doesn't exist with "
            f"vm_id: {id}, called by {self.user}")

        fake_volume = self.make_volume()
        fake_instance = InstanceFactory.create(
            id=id, user=self.user, boot_volume=fake_volume)

        self.assertEqual(
            fake_instance,
            Instance.objects.get_instance_by_untrusted_vm_id(
                id, self.user, self.feature))

        fake_user = UserFactory.create()
        with self.assertRaises(Http404):
            Instance.objects.get_instance_by_untrusted_vm_id(
                id, fake_user, self.feature)
        mock_logger.error.assert_called_with(
            "Trying to get a vm that doesn't belong "
            f"to {fake_user} with vm_id: {id}, "
            f"this vm belongs to {self.user}")

        # The special version used in anonymous callbacks
        self.assertEqual(
            fake_instance,
            Instance.objects.get_instance_by_untrusted_vm_id_2(
                id, self.feature))

        fake_feature = FeatureFactory.create()
        with self.assertRaises(Http404):
            Instance.objects.get_instance_by_untrusted_vm_id(
                id, self.user, fake_feature)
        mock_logger.error.assert_called_with(
            "Trying to get a vm that doesn't belong "
            f"to {fake_feature} with vm_id: {id}. "
            f"This vm belongs to {self.feature}")

        with self.assertRaises(Http404):
            instance = Instance.objects.get(id=id)
            instance.deleted = datetime.now(utc)
            instance.save()
            Instance.objects.get_instance_by_untrusted_vm_id(
                id, self.user, self.feature)
        mock_logger.error.assert_called_with(
            "Trying to get a vm that has been deleted with "
            f"vm_id: {id}, called by {self.user}")

        instance = Instance.objects.get(id=id)
        instance.deleted = None
        instance.save()
        instance.set_marked_for_deletion()
        Instance.objects.get_instance_by_untrusted_vm_id(
            id, self.user, self.feature)
        mock_logger.error.assert_called_with(
            "Got a vm that is marked for deletion "
            f"- vm_id: {id}, called by {self.user}")

    def test_get_live_instances(self):
        self.assertEqual([],
                         Instance.objects.get_live_instances(self.user, None))

        fake_volume = self.make_volume()
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)
        self.assertEqual([fake_instance],
                         Instance.objects.get_live_instances(self.user, None))

        fake_volume2 = self.make_volume()
        fake_instance2 = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume2)
        self.assertEqual([fake_instance, fake_instance2],
                         Instance.objects.get_live_instances(self.user, None))

        fake_instance2.deleted = datetime.now(utc)
        fake_instance2.save()
        self.assertEqual([fake_instance],
                         Instance.objects.get_live_instances(self.user, None))

        desktop_type2 = DesktopTypeFactory.create(
            id='desktop2', name='desktop2', feature=self.feature)
        fake_volume3 = self.make_volume(
            operating_system=desktop_type2.id,
            requesting_feature=desktop_type2.feature)
        fake_instance3 = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume3)
        self.assertEqual(
            [fake_instance],
            Instance.objects.get_live_instances(self.user,
                                                self.desktop_type))
        self.assertEqual(
            [fake_instance3],
            Instance.objects.get_live_instances(self.user,
                                                desktop_type2))


class ResizeModelTests(VMManagerModelTestBase):

    def test_resize_basics(self):
        id = uuid.uuid4()
        fake_volume = self.make_volume()
        fake_instance = InstanceFactory.create(
            id=id, user=self.user, boot_volume=fake_volume)

        now = datetime.now(utc)
        resize = ResizeFactory.create(instance=fake_instance)
        self.assertTrue(now <= resize.requested)
        self.assertFalse(resize.expired())
        self.assertEqual(f"Resize (Current) of Instance ({id}) "
                         f"requested on {resize.requested}",
                         str(resize))

        fake_instance.deleted = datetime.now(utc)
        fake_instance.save()
        self.assertTrue(resize.expired())
        self.assertEqual(f"Resize (Expired) of Instance ({id}) "
                         f"requested on {resize.requested}",
                         str(resize))

        fake_instance.deleted = None
        fake_instance.save()
        self.assertFalse(resize.expired())

        resize.reverted = now
        resize.save()
        self.assertTrue(resize.expired())
        self.assertEqual(f"Resize (Expired) of Instance ({id}) "
                         f"requested on {resize.requested}",
                         str(resize))

    def test_get_latest_resize(self):
        fake_volume = self.make_volume()
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        self.assertIsNone(Resize.objects.get_latest_resize(fake_instance))

        resize = ResizeFactory.create(instance=fake_instance)

        self.assertEqual(resize,
                         Resize.objects.get_latest_resize(fake_instance))

        resize2 = ResizeFactory.create(instance=fake_instance)

        self.assertEqual(resize2,
                         Resize.objects.get_latest_resize(fake_instance))

        fake_instance2 = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)

        ResizeFactory.create(instance=fake_instance2)

        self.assertEqual(resize2,
                         Resize.objects.get_latest_resize(fake_instance))

    def test_set_expires(self):
        fake_volume = self.make_volume()
        fake_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=fake_volume)
        resize = ResizeFactory.create(instance=fake_instance)

        self.assertIsNone(resize.expiration)

        now = datetime.now(utc)
        resize.set_expires(now)
        self.assertIsNotNone(resize.expiration)
        self.assertEqual(now, resize.expiration.expires)
        self.assertEqual(0, resize.expiration.stage)
        self.assertIsNotNone(resize.expiration.stage_date)

        now = datetime.now(utc)
        resize.set_expires(now)
        self.assertIsNotNone(resize.expiration)
        self.assertEqual(now, resize.expiration.expires)
        self.assertEqual(0, resize.expiration.stage)
        self.assertIsNotNone(resize.expiration.stage_date)

        resize.set_expires(None)
        self.assertIsNone(resize.expiration)


class VMStatusModelTests(VMManagerModelTestBase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.volume = self.make_volume()
        self.instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=self.volume)

    def make_vmstatus(self, **kwargs):
        my_kwargs = {
            'instance': self.instance,
            'user': self.user,
            'operating_system': self.desktop_type.id,
            'requesting_feature': self.desktop_type.feature
        }
        my_kwargs.update(kwargs)
        return VMStatusFactory.create(**my_kwargs)

    def test_get_latest_vm_status(self):
        self.assertIsNone(VMStatus.objects.get_latest_vm_status(
            self.user, self.desktop_type))

        vmstatus = self.make_vmstatus()
        self.assertEqual(vmstatus,
                         VMStatus.objects.get_latest_vm_status(
                             self.user, self.desktop_type))

        vmstatus2 = self.make_vmstatus()
        self.assertEqual(vmstatus2,
                         VMStatus.objects.get_latest_vm_status(
                             self.user, self.desktop_type))

    def test_get_vm_status_by_volume(self):
        other_feature = FeatureFactory.create()
        with self.assertRaises(Http404):
            VMStatus.objects.get_vm_status_by_volume(
                self.volume, other_feature)

        other_volume = self.make_volume()
        with self.assertRaises(Instance.DoesNotExist):
            VMStatus.objects.get_vm_status_by_volume(
                other_volume, self.feature)

        vmstatus = self.make_vmstatus()
        self.assertEqual(vmstatus,
                         VMStatus.objects.get_vm_status_by_volume(
                             self.volume, self.feature))

        self.make_vmstatus()
        with self.assertRaises(VMStatus.MultipleObjectsReturned) as cm:
            VMStatus.objects.get_vm_status_by_volume(
                self.volume, self.feature)
        self.assertEqual("Multiple vm_statuses found in the database "
                         f"with instance={self.instance}",
                         str(cm.exception))

    def test_get_vm_status_by_instance(self):
        other_instance = InstanceFactory.create(
            id=uuid.uuid4(), user=self.user, boot_volume=self.volume)
        with self.assertRaises(VMStatus.DoesNotExist):
            VMStatus.objects.get_vm_status_by_instance(
                other_instance, self.feature)
        self.assertIsNone(VMStatus.objects.get_vm_status_by_instance(
            other_instance, self.feature, allow_missing=True))

        vmstatus = self.make_vmstatus()
        self.assertEqual(vmstatus,
                         VMStatus.objects.get_vm_status_by_instance(
                             self.instance, self.feature))

        self.make_vmstatus()
        with self.assertRaises(VMStatus.MultipleObjectsReturned) as cm:
            VMStatus.objects.get_vm_status_by_instance(
                self.instance, self.feature)
        self.assertEqual("Multiple vm_statuses found in the database "
                         f"with instance={self.instance}",
                         str(cm.exception))
