from unittest.mock import Mock

import uuid

from django.conf import settings

from vm_manager.tests.common import UUID_1, UUID_2


class Fake(object):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        return f"{self.__class__} id={self.id}}}"

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.id == other.id


class FakeFlavor(Fake):
    pass


class FakeVolume(Fake):
    pass


class FakeServer(Fake):
    pass


FLAVORS = [
    FakeFlavor(id=uuid.uuid4(), name='m3.medium',
               ram='1', disk='1', vcpus='1'),
    FakeFlavor(id=uuid.uuid4(), name='m3.xxlarge',
               ram='2', disk='2', vcpus='2'),
]

VOLUMES = [
    FakeVolume(id='1', name='m3.medium', ram='1', disk='1', vcpus='1'),
]


class FakeNectar(object):
    def __init__(self):
        self.nova = Mock()
        self.nova.flavors.list = Mock(return_value=FLAVORS)
        self.nova.servers.create = Mock(
            return_value=FakeServer(id=UUID_1))

        self.allocation = Mock()
        self.keystone = Mock()
        self.glance = Mock()

        self.cinder = Mock()
        self.cinder.volumes.list = Mock(return_value=VOLUMES)
        self.cinder.volumes.create = Mock(
            return_value=FakeVolume(id=UUID_1))

        net_id = UUID_2
        self.VM_PARAMS = {
            "size": 20,
            "metadata_volume": {'readonly': 'False'},
            "availability_zone_volume": settings.OS_AVAILABILITY_ZONE,
            "availability_zone_server": settings.OS_AVAILABILITY_ZONE,
            "block_device_mapping": [{
                'source_type': "volume",
                'destination_type': 'volume',
                'delete_on_termination': False,
                'uuid': None,
                'boot_index': '0',
                'volume_size': 20,
            }],
            "id_net": net_id,
            "list_net": [{'net-id': net_id}],
        }
