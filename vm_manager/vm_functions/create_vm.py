import copy
import crypt
from datetime import datetime, timedelta
import logging

import cinderclient
import django_rq

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.timezone import utc

from vm_manager.constants import VOLUME_CREATION_TIMEOUT, \
    INSTANCE_LAUNCH_TIMEOUT, NO_VM, VM_SHELVED, VOLUME_AVAILABLE, ACTIVE
from vm_manager.utils.expiry import InstanceExpiryPolicy
from vm_manager.utils.utils import get_nectar, generate_server_name, \
    generate_hostname, generate_password
from vm_manager.models import Instance, Volume, VMStatus

from researcher_desktop.models import AvailabilityZone

from guacamole.models import GuacamoleConnection

logger = logging.getLogger(__name__)


def launch_vm_worker(user, desktop_type, zone):
    desktop_id = desktop_type.id
    logger.info(f'Launching {desktop_id} VM for {user.username}')

    instance = Instance.objects.get_instance(user, desktop_type)
    if instance:
        vm_status = VMStatus.objects.get_vm_status_by_instance(
            instance, desktop_type.feature)
        if vm_status.status != NO_VM:
            msg = f"A {desktop_id} VM for {user} already exists"
            logger.error(msg)
            raise RuntimeWarning(msg)

    volume = _create_volume(user, desktop_type, zone)
    if volume:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(timedelta(seconds=5), wait_to_create_instance,
                             user, desktop_type, volume,
                             datetime.now(utc))
        logger.info(f'{desktop_id} VM creation scheduled '
                    f'for {user.username}')


def _create_volume(user, desktop_type, zone):
    desktop_id = desktop_type.id
    requesting_feature = desktop_type.feature
    volume = Volume.objects.get_volume(user, desktop_type)
    if volume:
        # Check that the volume still exists in Cinder, and that it
        # has status 'available', and is in the expected AZ.
        n = get_nectar()
        try:
            cinder_volume = n.cinder.volumes.get(volume.id)
            if cinder_volume.status != VOLUME_AVAILABLE:
                logger.error(f"Cinder volume for {volume} in wrong state "
                             f"{cinder_volume.status}. Needs manual cleanup.")
                volume.error(f"Cinder volume in state {cinder_volume.status}")
                return None
            if cinder_volume.availability_zone != zone.name:
                logger.error(f"Cinder volume for {volume} in wrong AZ. "
                             "Needs manual cleanup")
                volume.error("Cinder volume in wrong AZ")
                return None
        except cinderclient.exceptions.NotFound:
            logger.error(f"Cinder volume missing for {volume}. "
                         "Needs manual cleanup.")
            volume.error("Cinder volume missing")
            return None

        vm_status = VMStatus.objects.get_vm_status_by_volume(
            volume, requesting_feature)
        if vm_status.status == VM_SHELVED:
            if volume.archived_at:
                logger.error("Cannot launch shelved volume marked as "
                             f"archived: {volume}")
                return None

            volume.set_expires(None)
            return volume
        else:
            # It looks like a volume exists for the user, but it is not
            # shelved.   We need to either delete it, or do something to
            # recover it; i.e. make it unshelvable.
            logger.error(f"VMstatus {vm_status.status} inconsistent with "
                         f"existing {volume} in _create_volume.  Needs "
                         "manual cleanup.")
            return None

    # Either there is no existing volume, or we have decided to ignore it
    # and make a new one for the user.

    vm_status = VMStatus.objects.get_latest_vm_status(user, desktop_type)
    if vm_status:
        vm_status.status_progress = 25
        vm_status.status_message = 'Creating volume'
        vm_status.save()

    name = generate_server_name(user.username, desktop_id)
    source_volume_id = _get_source_volume_id(desktop_type, zone)

    n = get_nectar()
    volume_result = n.cinder.volumes.create(
        source_volid=source_volume_id,
        size=desktop_type.volume_size,
        name=name,
        metadata={'readonly': 'False'},
        availability_zone=zone.name)
    n.cinder.volumes.set_bootable(volume=volume_result, flag=True)

    # Create record in DB
    volume = Volume(
        id=volume_result.id, user=user,
        image=source_volume_id,
        requesting_feature=requesting_feature,
        operating_system=desktop_id,
        zone=zone.name,
        flavor=desktop_type.default_flavor.id)
    volume.save()

    # Add the volume's hostname to the volume's metadata on openstack
    n.cinder.volumes.set_metadata(
        volume=volume_result,
        metadata={
            'hostname': generate_hostname(volume.hostname_id, desktop_id),
            'user': user.email,
            'desktop': desktop_id,
            'environment': settings.ENVIRONMENT_NAME,
            'requesting_feature': requesting_feature.name,
        })
    return volume


def _get_source_volume_id(desktop_type, zone):
    n = get_nectar()
    res = n.cinder.volumes.list(
        search_opts={'name~': desktop_type.image_name,
                     'availability_zone': zone.name,
                     'status': VOLUME_AVAILABLE})
    # The 'name~' is supposed to be a "fuzzy match", but it doesn't work
    # as expected.  (Maybe it is a Cinder config thing?)  At any rate,
    # even if it did work, we still need to do our own filtering to
    # 1) ensure we have a prefix match, and 2) pick the latest (tested)
    # image based on the image metadata.
    candidates = res or []
    # Interim logic ...
    matches = sorted(
        [v for v in candidates if v.name.startswith(desktop_type.image_name)],
        key=lambda v: int(v.metadata.get('nectar_build', 0)), reverse=True)

    if len(matches) < 1:
        msg = (
            "No source volume with image names starting with "
            f"{desktop_type.image_name} in availability zone {zone.name})")
        logger.error(msg)
        raise RuntimeWarning(msg)

    match = matches[0]
    logger.debug(f"Found source volume: {match.name} ({match.id}) in "
                 f"availability zone {zone.name}")
    return match.id


def wait_to_create_instance(user, desktop_type, volume, start_time):
    n = get_nectar()
    now = datetime.now(utc)
    openstack_volume = n.cinder.volumes.get(volume_id=volume.id)
    logger.info(f"Volume created in {now-start_time}s; "
                f"volume status is {openstack_volume.status}")

    if openstack_volume.status == VOLUME_AVAILABLE:
        instance = _create_instance(user, desktop_type, volume)
        vm_status = VMStatus.objects.get_latest_vm_status(user, desktop_type)
        vm_status.instance = instance
        vm_status.status_progress = 50
        if volume.shelved_at:
            vm_status.status_message = 'Unshelving instance'
        else:
            vm_status.status_message = 'Volume created, launching instance'
        vm_status.save()

        volume.shelved_at = None
        volume.expiry = None
        volume.save()
        logger.info(f'{desktop_type.name} VM creation initiated '
                    f'for {user.username}')
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(timedelta(seconds=5), wait_for_instance_active,
                             user, desktop_type, instance,
                             datetime.now(utc))

    elif (now - start_time > timedelta(seconds=VOLUME_CREATION_TIMEOUT)):
        logger.error(f"Volume took too long to create: user:{user} "
                     f"desktop_id:{desktop_type.id} volume:{volume} "
                     f"volume.status:{openstack_volume.status} "
                     f"start_time:{start_time} "
                     f"datetime.now:{now}")
        msg = "Volume took too long to create"
        vm_status = VMStatus.objects.get_latest_vm_status(user, desktop_type)
        vm_status.status = NO_VM
        vm_status.status_message = msg
        vm_status.save()
        volume.error(msg)
        volume.save()
        raise TimeoutError(msg)

    else:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(timedelta(seconds=5), wait_to_create_instance,
                             user, desktop_type, volume, start_time)


def _create_instance(user, desktop_type, volume):
    n = get_nectar()
    desktop_id = desktop_type.id
    hostname = generate_hostname(volume.hostname_id, desktop_id)
    name = generate_server_name(user.username, desktop_id)

    # Reuse the previous username and password
    last_instance = Instance.objects.get_latest_instance_for_volume(volume)
    if last_instance:
        username = last_instance.username
        password = last_instance.password
    else:
        username = 'vdiuser'
        password = generate_password()

    metadata_server = {
        'allow_user': user.username,
        'environment': settings.ENVIRONMENT_NAME,
        'requesting_feature': desktop_type.feature.name,
    }

    block_device_mapping = [{
        'source_type': "volume",
        'destination_type': 'volume',
        'delete_on_termination': False,
        'uuid': volume.id,
        'boot_index': '0',
    }]

    zone = volume.zone
    network_id = AvailabilityZone.objects.get(name=zone).network_id
    nics = [{'net-id': network_id}]

    desktop_timezone = user.profile.timezone or settings.TIME_ZONE
    user_data_context = {
        'hostname': hostname,
        'notify_url': (settings.SITE_URL
                       + reverse('researcher_desktop:notify_vm')),
        'phone_home_url': (settings.SITE_URL
                           + reverse('researcher_desktop:phone_home')),
        'username': username,
        'password': crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512)),
        'timezone': desktop_timezone,
    }
    user_data = render_to_string('vm_manager/cloud-config',
                                 user_data_context)

    # Create instance in OpenStack
    launch_result = n.nova.servers.create(
        name=name,
        image='',
        flavor=desktop_type.default_flavor.id,
        userdata=user_data,
        security_groups=desktop_type.security_groups,
        block_device_mapping_v2=block_device_mapping,
        nics=nics,
        availability_zone=zone,
        meta=metadata_server,
        key_name=settings.OS_KEYNAME,
    )

    # Create guac connection
    full_name = user.get_full_name()
    desktop_name = desktop_type.name
    connection_name = f"{full_name}'s {desktop_name} desktop"
    connection_protocol = n.get_console_protocol()
    guac_connection = GuacamoleConnection.objects.create(
        connection_name=connection_name,
        protocol=connection_protocol)

    # Create record in DB
    instance = Instance.objects.create(
        id=launch_result.id, user=user, boot_volume=volume,
        guac_connection=guac_connection,
        username=username,
        password=password)

    logger.info(f"Completed creating {instance}")

    return instance


def wait_for_instance_active(user, desktop_type, instance, start_time):
    now = datetime.now(utc)
    if instance.check_active_status():
        logger.info(f"Instance {instance.id} is now {ACTIVE}")
        vm_status = VMStatus.objects.get_vm_status_by_instance(
            instance, desktop_type.feature)
        vm_status.status_progress = 75
        vm_status.status_message = 'Instance launched; waiting for boot'
        vm_status.save()
        instance.set_expires(
            InstanceExpiryPolicy().initial_expiry(now=instance.created))
    elif (now - start_time > timedelta(seconds=INSTANCE_LAUNCH_TIMEOUT)):
        logger.error(f"Instance took too long to launch: user:{user} "
                     f"desktop:{desktop_type.id} instance:{instance} "
                     f"instance.status:{instance.get_status()} "
                     f"start_time:{start_time} "
                     f"datetime.now:{now}")
        msg = "Instance took too long to launch"
        vm_status = VMStatus.objects.get_latest_vm_status(user, desktop_type)
        vm_status.status = NO_VM
        vm_status.status_message = msg
        vm_status.save()
        instance.error(msg)
    else:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(timedelta(seconds=5), wait_for_instance_active,
                             user, desktop_type, instance, start_time)


# TODO - Analyse for possible race conditions with create/delete
def extend_instance(user, vm_id, requesting_feature) -> str:
    instance = Instance.objects.get_instance_by_untrusted_vm_id(
        vm_id, user, requesting_feature)
    logger.info("Extending the expiration of boosted "
                f"{instance.boot_volume.operating_system} vm "
                f"for user {user.username}")
    instance.set_expires(InstanceExpiryPolicy().new_expiry(instance))
    return str(instance)
