import copy
import django_rq
import logging
import re

from datetime import datetime, timedelta, timezone
from django.conf import settings
from django.urls import reverse

from researcher_workspace.settings import ENVIRONMENT_NAME

from vm_manager.constants import HOSTNAME_PLACEHOLDER, HOSTNAME_URL_PLACEHOLDER, \
    USERNAME_PLACEHOLDER, VOLUME_CREATION_TIMEOUT, DOMAIN_PLACEHOLDER, NO_VM, VM_OKAY, LINUX, WINDOWS
from vm_manager.utils.utils import get_nectar, generate_server_name, generate_hostname, generate_hostname_url,\
    get_domain
from vm_manager.models import Instance, Volume, VMStatus

from guacamole.models import GuacamoleConnection

logger = logging.getLogger(__name__)


def launch_vm_worker(user, vm_info, requesting_feature):
    operating_system = vm_info['operating_system']
    logger.info(f'Launching {operating_system} VM for {user.username}')

    instance = Instance.objects.get_instance(user, operating_system, requesting_feature)
    if instance:
        vm_status = VMStatus.objects.get_vm_status_by_instance(instance, requesting_feature)
        if vm_status.status != NO_VM:
            msg = f"A {operating_system} VM for {user} already exists"
            logger.error(msg)
            raise RuntimeWarning(msg)

    volume = _create_volume(user, vm_info, requesting_feature)
    scheduler = django_rq.get_scheduler('default')
    scheduler.enqueue_in(timedelta(seconds=5), wait_to_create_instance, user, vm_info, volume,
                         datetime.now(timezone.utc), requesting_feature)
    logger.info(f'{operating_system} VM created for {user.username}')


def _create_volume(user, vm_info, requesting_feature):
    operating_system = vm_info['operating_system']

    volume = Volume.objects.get_volume(user, operating_system, requesting_feature)
    logger.info(str(volume))
    if volume:
        vm_status = VMStatus.objects.get_vm_status_by_volume(volume, requesting_feature)
        if vm_status.status != NO_VM:
            return volume

    n = get_nectar()
    name = generate_server_name(user.username, operating_system)

    volume_result = n.cinder.volumes.create(source_volid=vm_info['source_volume'], size=n.VM_PARAMS["size"],
                                            name=name, metadata=n.VM_PARAMS["metadata_volume"],
                                            availability_zone=n.VM_PARAMS["availability_zone_volume"])
    n.cinder.volumes.set_bootable(volume=volume_result, flag=True)

    # Create record in DB
    volume = Volume(id=volume_result.id, user=user, image=vm_info['source_volume'], requesting_feature=requesting_feature,
                    operating_system=operating_system, flavor=vm_info['flavor'])
    volume.save()

    # Add the volume's hostname to the volume's metadata on openstack
    n.cinder.volumes.set_metadata(volume=volume_result,
                                  metadata={'hostname': generate_hostname(volume.hostname_id, operating_system),
                                            'allow_user': user.username + re.search("@.*", user.email).group(),
                                            'environment': ENVIRONMENT_NAME,
                                            'requesting_feature': requesting_feature.name,
                                            })
    return volume


def wait_to_create_instance(user, vm_info, volume, start_time, requesting_feature):
    n = get_nectar()
    openstack_volume = n.cinder.volumes.get(volume_id=volume.id)
    logger.info(f'second: {datetime.now(timezone.utc)-start_time}; volume status:{openstack_volume.status}')
    operating_system = vm_info['operating_system']

    if openstack_volume.status == 'available':
        instance = _create_instance(user, vm_info, volume)
        vm_status = VMStatus.objects.get_latest_vm_status(user, operating_system, requesting_feature)
        vm_status.instance = instance
        if volume.shelved:
            vm_status.status = VM_OKAY
        vm_status.save()

        # Set the Shelved flag to False
        volume.shelved = False
        volume.save()
        return
    if datetime.now(timezone.utc)-start_time > timedelta(seconds=VOLUME_CREATION_TIMEOUT):
        logger.error(f"Volume took too long to create: user:{user} operating_system:{operating_system} volume:{volume}"
            f" volume.status:{openstack_volume.status} start_time:{start_time} datetime.now:{datetime.now(timezone.utc)}")
        vm_status = VMStatus.objects.get_latest_vm_status(user, operating_system, requesting_feature)
        vm_status.status = NO_VM
        vm_status.save()
        msg = "Volume took too long to create"
        volume.error(msg)
        volume.save()
        raise TimeoutError(msg)
    else:
        scheduler = django_rq.get_scheduler('default')
        scheduler.enqueue_in(timedelta(seconds=5), wait_to_create_instance, user, vm_info, volume, start_time, requesting_feature)


def _create_instance(user, vm_info, volume):
    n = get_nectar()
    operating_system = vm_info['operating_system']
    hostname = generate_hostname(volume.hostname_id, operating_system)
    hostname_url = generate_hostname_url(volume.hostname_id, operating_system)

    metadata_server = {
        'allow_user': user.username + re.search("@.*", user.email).group(),
        'environment': ENVIRONMENT_NAME,
        'requesting_feature': volume.requesting_feature.name,
    }

    block_device_mapping = copy.deepcopy(n.VM_PARAMS["block_device_mapping"])
    block_device_mapping[0]["uuid"] = volume.id

    user_data_script = vm_info['user_data_script'] \
        .replace(HOSTNAME_PLACEHOLDER, hostname).replace(HOSTNAME_URL_PLACEHOLDER, hostname_url) \
        .replace(USERNAME_PLACEHOLDER, user.username).replace(DOMAIN_PLACEHOLDER, get_domain(user))

    # Create instance in OpenStack
    launch_result = n.nova.servers.create(
        name=hostname, image="", flavor=vm_info['flavor'],
        userdata=user_data_script, security_groups=vm_info['security_groups'],
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
