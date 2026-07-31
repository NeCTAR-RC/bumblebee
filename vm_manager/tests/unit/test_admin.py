from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import uuid

from django.test import RequestFactory, TestCase, override_settings

from researcher_desktop.tests.factories import DesktopTypeFactory
from researcher_workspace.tests.factories import FeatureFactory, UserFactory
from vm_manager.admin import (
    ErrorStatusFilter, Expirable, ExpirationAdmin, InstanceAdmin,
    ResizeAdmin, VMStatusAdmin, VolumeAdmin, admin_archive_instances,
    admin_archive_shelved_volumes, admin_check_vmstatuses,
    admin_delete_instances, admin_delete_shelved_instances,
    admin_delete_shelved_volumes, admin_downsize_resizes,
    admin_repair_instance_errors, admin_repair_volume_errors,
    admin_shelve_instances, clear_expiry, set_expiry,
)
from vm_manager.constants import NO_VM, VM_OKAY
from vm_manager.models import Expiration, Instance, Resize, VMStatus, Volume
from vm_manager.tests.factories import (
    InstanceFactory, ResizeFactory, VMStatusFactory, VolumeFactory,
)

utc = timezone.utc


class _AdminBaseSetup(TestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.feature = FeatureFactory.create(app_name='feature_x')
        self.desktop_type = DesktopTypeFactory.create(
            id='dt', name='dt', feature=self.feature)
        self.factory = RequestFactory()
        self.request = self.factory.post("/admin/")
        self.request.user = self.user

    def _make_volume(self, **kwargs):
        params = dict(
            id=uuid.uuid4(), user=self.user,
            operating_system='ubuntu', requesting_feature=self.feature,
            zone='QRIScloud',
        )
        params.update(kwargs)
        with patch('vm_manager.models._create_hostname_id') as m:
            m.return_value = uuid.uuid4().hex[:6]
            return VolumeFactory.create(**params)

    def _make_instance(self, volume=None, **kwargs):
        if volume is None:
            volume = self._make_volume()
        params = dict(
            id=uuid.uuid4(), user=self.user, boot_volume=volume,
        )
        params.update(kwargs)
        return InstanceFactory.create(**params)


class ExpiryActionsTests(_AdminBaseSetup):
    def test_set_expiry_volume_instance_resize(self):
        volume = self._make_volume()
        instance = self._make_instance(volume=volume)
        resize = ResizeFactory.create(instance=instance)
        # Run set_expiry across all three resource types
        set_expiry(None, self.request, [volume])
        volume.refresh_from_db()
        self.assertIsNotNone(volume.expiration)
        set_expiry(None, self.request, [instance])
        instance.refresh_from_db()
        self.assertIsNotNone(instance.expiration)
        set_expiry(None, self.request, [resize])
        resize.refresh_from_db()
        self.assertIsNotNone(resize.expiration)

    def test_set_expiry_unknown_type_raises(self):
        with self.assertRaises(Exception):
            set_expiry(None, self.request, [object()])

    def test_clear_expiry(self):
        volume = self._make_volume()
        from vm_manager.utils.expiry import VolumeExpiryPolicy
        volume.set_expires(VolumeExpiryPolicy().initial_expiry())
        clear_expiry(None, self.request, [volume])
        volume.refresh_from_db()
        self.assertIsNone(volume.expiration)


@patch('vm_manager.admin.admin_downsize_resize')
@patch('vm_manager.admin.admin_delete_instance_and_volume')
@patch('vm_manager.admin.admin_archive_instance_and_volume')
@patch('vm_manager.admin.admin_repair_volume_error')
@patch('vm_manager.admin.admin_delete_volume')
@patch('vm_manager.admin.admin_archive_volume')
@patch('vm_manager.admin.admin_shelve_instance')
@patch('vm_manager.admin.admin_repair_instance_error')
@patch('vm_manager.admin.admin_check_vmstatus')
class AdminActionsTests(_AdminBaseSetup):
    def test_admin_downsize_resizes(self, *mocks):
        volume = self._make_volume()
        instance = self._make_instance(volume=volume)
        resize = ResizeFactory.create(instance=instance, reverted=None)
        admin_downsize_resizes(None, self.request, [resize])
        # admin_downsize_resize is the 9th @patch from top -> last decorator
        # so it's mocks[-1]
        # (decorator order is bottom-up; last applied = first arg)
        # Check at least one mock was called
        called = any(m.called for m in mocks)
        self.assertTrue(called)

    def test_admin_delete_instances(self, *mocks):
        volume = self._make_volume()
        instance = self._make_instance(volume=volume)
        admin_delete_instances(None, self.request, [instance])
        # At least one mock called
        self.assertTrue(any(m.called for m in mocks))

    def test_admin_archive_instances(self, *mocks):
        volume = self._make_volume()
        instance = self._make_instance(volume=volume)
        admin_archive_instances(None, self.request, [instance])
        self.assertTrue(any(m.called for m in mocks))

    def test_admin_repair_volume_errors(self, *mocks):
        volume = self._make_volume()
        admin_repair_volume_errors(None, self.request, [volume])
        self.assertTrue(any(m.called for m in mocks))

    def test_admin_repair_volume_errors_marked(self, *mocks):
        # Volumes marked for deletion are still passed to the repair
        # function; only deleted ones are skipped.
        volume = self._make_volume(marked_for_deletion=datetime.now(utc))
        admin_repair_volume_errors(None, self.request, [volume])
        self.assertTrue(any(m.called for m in mocks))

    def test_admin_repair_volume_errors_deleted(self, *mocks):
        volume = self._make_volume(deleted=datetime.now(utc))
        admin_repair_volume_errors(None, self.request, [volume])
        self.assertFalse(any(m.called for m in mocks))

    def test_admin_delete_shelved_volumes(self, *mocks):
        volume = self._make_volume(shelved_at=datetime.now(utc))
        admin_delete_shelved_volumes(None, self.request, [volume])
        self.assertTrue(any(m.called for m in mocks))

    def test_admin_archive_shelved_volumes(self, *mocks):
        volume = self._make_volume(shelved_at=datetime.now(utc))
        admin_archive_shelved_volumes(None, self.request, [volume])
        self.assertTrue(any(m.called for m in mocks))

    def test_admin_shelve_instances(self, *mocks):
        volume = self._make_volume()
        instance = self._make_instance(volume=volume)
        admin_shelve_instances(None, self.request, [instance])
        self.assertTrue(any(m.called for m in mocks))

    def test_admin_delete_shelved_instances(self, *mocks):
        volume = self._make_volume(shelved_at=datetime.now(utc))
        instance = self._make_instance(volume=volume,
                                       deleted=datetime.now(utc))
        admin_delete_shelved_instances(None, self.request, [instance])
        self.assertTrue(any(m.called for m in mocks))

    def test_admin_repair_instance_errors(self, *mocks):
        volume = self._make_volume()
        instance = self._make_instance(volume=volume)
        admin_repair_instance_errors(None, self.request, [instance])
        self.assertTrue(any(m.called for m in mocks))

    def test_admin_repair_instance_errors_marked(self, *mocks):
        # Instances marked for deletion (e.g. by error(gone=True) or
        # a delete workflow that died) are still passed to the repair
        # function; only deleted ones are skipped.
        volume = self._make_volume()
        instance = self._make_instance(
            volume=volume, marked_for_deletion=datetime.now(utc))
        admin_repair_instance_errors(None, self.request, [instance])
        self.assertTrue(any(m.called for m in mocks))

    def test_admin_repair_instance_errors_deleted(self, *mocks):
        volume = self._make_volume()
        instance = self._make_instance(
            volume=volume, deleted=datetime.now(utc))
        admin_repair_instance_errors(None, self.request, [instance])
        self.assertFalse(any(m.called for m in mocks))

    def test_admin_check_vmstatuses(self, *mocks):
        volume = self._make_volume()
        instance = self._make_instance(volume=volume)
        vms = VMStatusFactory.create(
            user=self.user, requesting_feature=self.feature,
            instance=instance, operating_system='ubuntu', status=VM_OKAY)
        admin_check_vmstatuses(None, self.request, [vms])
        self.assertTrue(any(m.called for m in mocks))


class ExpirableTests(_AdminBaseSetup):
    def test_expiration_link_none(self):
        volume = self._make_volume()
        link = Expirable().expiration_link(volume)
        self.assertEqual('None', link)

    def test_expiration_link_with_expiration(self):
        from vm_manager.utils.expiry import VolumeExpiryPolicy
        volume = self._make_volume()
        volume.set_expires(VolumeExpiryPolicy().initial_expiry())
        link = Expirable().expiration_link(volume)
        self.assertIn("Open", link)


class ErrorStatusFilterTests(_AdminBaseSetup):
    def test_lookups(self):
        f = ErrorStatusFilter(self.request, {}, Volume, VolumeAdmin)
        lookups = f.lookups(self.request, None)
        self.assertEqual(3, len(lookups))

    def test_queryset_error(self):
        live_err = self._make_volume(error_flag=datetime.now(utc))
        deleted_err = self._make_volume(
            error_flag=datetime.now(utc), deleted=datetime.now(utc))
        f = ErrorStatusFilter(
            self.request, {'error_status': ['error']}, Volume, VolumeAdmin)
        result = f.queryset(self.request, Volume.objects.all())
        ids = [v.id for v in result]
        self.assertIn(live_err.id, ids)
        self.assertNotIn(deleted_err.id, ids)

    def test_queryset_deleted(self):
        live_err = self._make_volume(error_flag=datetime.now(utc))
        deleted_err = self._make_volume(
            error_flag=datetime.now(utc), deleted=datetime.now(utc))
        f = ErrorStatusFilter(
            self.request, {'error_status': ['deleted']}, Volume, VolumeAdmin)
        result = f.queryset(self.request, Volume.objects.all())
        ids = [v.id for v in result]
        self.assertNotIn(live_err.id, ids)
        self.assertIn(deleted_err.id, ids)

    def test_queryset_all(self):
        live_err = self._make_volume(error_flag=datetime.now(utc))
        deleted_err = self._make_volume(
            error_flag=datetime.now(utc), deleted=datetime.now(utc))
        f = ErrorStatusFilter(
            self.request, {'error_status': ['all']}, Volume, VolumeAdmin)
        result = f.queryset(self.request, Volume.objects.all())
        self.assertEqual(2, result.count())


class AdminPermissionTests(_AdminBaseSetup):

    @override_settings(DEBUG=True)
    def test_expiration_admin_delete_perm_in_debug(self):
        admin_obj = ExpirationAdmin(Expiration, None)
        self.assertTrue(admin_obj.has_delete_permission(self.request))

    @override_settings(DEBUG=False)
    def test_expiration_admin_delete_perm_not_debug(self):
        admin_obj = ExpirationAdmin(Expiration, None)
        self.assertFalse(admin_obj.has_delete_permission(self.request))

    @override_settings(DEBUG=False)
    def test_instance_admin_delete_perm_marked_for_deletion(self):
        admin_obj = InstanceAdmin(Instance, None)
        instance = self._make_instance()
        instance.set_marked_for_deletion()
        self.assertFalse(
            admin_obj.has_delete_permission(self.request, obj=instance))

    @override_settings(DEBUG=False)
    def test_instance_admin_delete_perm_no_obj(self):
        admin_obj = InstanceAdmin(Instance, None)
        self.assertFalse(admin_obj.has_delete_permission(self.request))

    @override_settings(DEBUG=True)
    def test_volume_admin_delete_perm(self):
        admin_obj = VolumeAdmin(Volume, None)
        self.assertTrue(admin_obj.has_delete_permission(self.request))

    @override_settings(DEBUG=True)
    def test_resize_admin_delete_perm(self):
        admin_obj = ResizeAdmin(Resize, None)
        self.assertTrue(admin_obj.has_delete_permission(self.request))

    @override_settings(DEBUG=True)
    def test_vmstatus_admin_delete_perm(self):
        admin_obj = VMStatusAdmin(VMStatus, None)
        self.assertTrue(admin_obj.has_delete_permission(self.request))


class InstanceAdminGetRequestingFeatureTest(_AdminBaseSetup):
    def test_get_requesting_feature(self):
        volume = self._make_volume()
        instance = self._make_instance(volume=volume)
        admin_obj = InstanceAdmin(Instance, None)
        self.assertEqual(self.feature,
                         admin_obj.get_requesting_feature(instance))


class VMStatusAdminResponseChangeTests(_AdminBaseSetup):

    def _make_vmstatus(self, instance=None):
        return VMStatusFactory.create(
            user=self.user, requesting_feature=self.feature,
            instance=instance, operating_system='ubuntu', status=VM_OKAY)

    def test_response_change_set_vm_okay_with_instance(self):
        volume = self._make_volume()
        instance = self._make_instance(volume=volume)
        instance.error("oops")
        volume.error("oops too")
        vms = self._make_vmstatus(instance=instance)
        request = self.factory.post("/admin/", data={'_set_vm_okay': '1'})
        request.user = self.user
        # Set up messages backend
        from django.contrib.messages.storage.fallback import FallbackStorage
        request.session = MagicMock()
        request._messages = FallbackStorage(request)
        admin_obj = VMStatusAdmin(VMStatus, MagicMock())
        response = admin_obj.response_change(request, vms)
        self.assertEqual(302, response.status_code)
        vms.refresh_from_db()
        self.assertEqual(VM_OKAY, vms.status)
        instance.refresh_from_db()
        self.assertIsNone(instance.error_flag)

    def test_response_change_set_vm_okay_no_instance(self):
        vms = self._make_vmstatus(instance=None)
        request = self.factory.post("/admin/", data={'_set_vm_okay': '1'})
        request.user = self.user
        from django.contrib.messages.storage.fallback import FallbackStorage
        request.session = MagicMock()
        request._messages = FallbackStorage(request)
        admin_obj = VMStatusAdmin(VMStatus, MagicMock())
        response = admin_obj.response_change(request, vms)
        self.assertEqual(302, response.status_code)
        vms.refresh_from_db()
        self.assertEqual(NO_VM, vms.status)

    def test_response_change_default(self):
        vms = self._make_vmstatus()
        request = self.factory.post("/admin/", data={})
        request.user = self.user
        from django.contrib.messages.storage.fallback import FallbackStorage
        request.session = MagicMock()
        request._messages = FallbackStorage(request)
        admin_obj = VMStatusAdmin(VMStatus, MagicMock())
        # default response_change calls super, which redirects
        with patch.object(VMStatusAdmin.__bases__[0], 'response_change',
                          return_value=MagicMock(status_code=302)):
            response = admin_obj.response_change(request, vms)
        self.assertEqual(302, response.status_code)
