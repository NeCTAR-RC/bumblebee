import copy
import django_rq
import logging
import re

from datetime import datetime, timedelta, timezone
from django.conf import settings
from django.urls import reverse

from researcher_workspace.settings import ENVIRONMENT_NAME

from vm_manager.constants import HOSTNAME_PLACEHOLDER, HOSTNAME_URL_PLACEHOLDER, \
    USERNAME_PLACEHOLDER, VOLUME_CREATION_TIMEOUT, DOMAIN_PLACEHOLDER, NO_VM, VM_OKAY, LINUX
from vm_manager.utils.utils import get_nectar, generate_server_name, generate_hostname, generate_hostname_url,\
    get_domain
from vm_manager.models import Instance, Volume, VMStatus

from guacamole.models import GuacamoleConnection

logger = logging.getLogger(__name__)


def launch_vm_worker(user, desktop_type):
    operating_system = desktop_type.id
    logger.info(f'Launching {operating_system} VM for {user.username}')

    instance = Instance.objects.get_instance(user, desktop_type)
    if instance:
        vm_status = VMStatus.objects.get_vm_status_by_instance(
            instance, requesting_feature)
        if vm_status.status != NO_VM:
            msg = f"A {operating_system} VM for {user} already exists"
            logger.error(msg)
            raise RuntimeWarning(msg)

    volume = _create_volume(user, desktop_type)
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=5), wait_to_create_instance,
                         user, desktop_type, volume,
                         datetime.now(timezone.utc))
    logger.info(f'{operating_system} VM creation scheduled '
                f'for {user.username}')


def _create_volume(user, desktop_type):
    operating_system = desktop_type.id
    requesting_feature = desktop_type.feature
    volume = Volume.objects.get_volume(user, desktop_type)
    if volume:
        vm_status = VMStatus.objects.get_vm_status_by_volume(
            volume, requesting_feature)
        if vm_status.status != NO_VM:
            return volume

    n = get_nectar()
    name = generate_server_name(user.username, operating_system)
    volume_result = n.cinder.volumes.create(
        source_volid=desktop_type.source_volume_id,
        size=n.VM_PARAMS["size"],
        name=name, metadata=n.VM_PARAMS["metadata_volume"],
        availability_zone=n.VM_PARAMS["availability_zone_volume"])
    n.cinder.volumes.set_bootable(volume=volume_result, flag=True)

    # Create record in DB
    volume = Volume(
        id=volume_result.id, user=user,
        image=desktop_type.source_volume_id,
        requesting_feature=requesting_feature,
        operating_system=operating_system,
        flavor=desktop_type.default_flavor_id)
    volume.save()

    # Add the volume's hostname to the volume's metadata on openstack
    n.cinder.volumes.set_metadata(
        volume=volume_result,
        metadata={
            'hostname': generate_hostname(volume.hostname_id,
                                          operating_system),
            'allow_user': user.username + re.search("@.*", user.email).group(),
            'environment': ENVIRONMENT_NAME,
            'requesting_feature': requesting_feature.name,
        })
    return volume


def wait_to_create_instance(user, desktop_type, volume, start_time):
    n = get_nectar()
    openstack_volume = n.cinder.volumes.get(volume_id=volume.id)
    logger.info(f"Volume created in {datetime.now(timezone.utc)-start_time}s; "
                f"volume status is {openstack_volume.status}")

    if openstack_volume.status == 'available':
        instance = _create_instance(user, desktop_type, volume)
        vm_status = VMStatus.objects.get_latest_vm_status(user, desktop_type)
        vm_status.instance = instance
        if volume.shelved:
            vm_status.status = VM_OKAY
        vm_status.save()

        # Set the Shelved flag to False
        volume.shelved = False
        volume.save()
        logger.info(f'{desktop_type.name} VM creation initiated '
                    f'for {user.username}')
        return
    
    if (datetime.now(timezone.utc)-start_time >
        timedelta(seconds=VOLUME_CREATION_TIMEOUT)):
        os = desktop_type.id
        logger.error(f"Volume took too long to create: user:{user} "
                     f"operating_system:{os} volume:{volume} "
                     f"volume.status:{openstack_volume.status} "
                     f"start_time:{start_time} "
                     f"datetime.now:{datetime.now(timezone.utc)}")
        vm_status = VMStatus.objects.get_latest_vm_status(user, desktop_type)
        vm_status.status = NO_VM
        vm_status.save()
        msg = "Volume took too long to create"
        volume.error(msg)
        volume.save()
        raise TimeoutError(msg)
    else:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(timedelta(seconds=5), wait_to_create_instance,
                             user, desktop_type, volume, start_time)


def _create_instance(user, desktop_type, volume):
    n = get_nectar()
    operating_system = desktop_type.id
    hostname = generate_hostname(volume.hostname_id, operating_system)
    hostname_url = generate_hostname_url(volume.hostname_id, operating_system)

    metadata_server = {
        'allow_user': user.username + re.search("@.*", user.email).group(),
        'environment': ENVIRONMENT_NAME,
        'requesting_feature': desktop_type.feature.name,
    }

    block_device_mapping = copy.deepcopy(n.VM_PARAMS["block_device_mapping"])
    block_device_mapping[0]["uuid"] = volume.id

    user_data_script = desktop_type.user_data_script \
        .replace(HOSTNAME_PLACEHOLDER, hostname) \
        .replace(HOSTNAME_URL_PLACEHOLDER, hostname_url) \
        .replace(USERNAME_PLACEHOLDER, user.username) \
        .replace(DOMAIN_PLACEHOLDER, get_domain(user))

    # Create instance in OpenStack
    launch_result = n.nova.servers.create(
        name=hostname, image="", flavor=desktop_type.default_flavor_id,
        userdata=user_data_script,
        security_groups=desktop_type.security_groups,
        key_name=settings.OS_KEYNAME, block_device_mapping_v1=None,
        block_device_mapping_v2=block_device_mapping,
        nics=n.VM_PARAMS["list_net"],
        availability_zone=n.VM_PARAMS["availability_zone_server"],
        meta=metadata_server)

    # Create guac connection
    guac_connection = GuacamoleConnection.objects.create(
        connection_name=launch_result.id)

    # Create record in DB
    instance = Instance.objects.create(
        id=launch_result.id, user=user, boot_volume=volume,
        guac_connection=guac_connection)

    logger.info(f"Completed creating {instance}")

    return instance
