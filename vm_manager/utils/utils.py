from datetime import datetime, timedelta, timezone

from cinderclient import client as cinder_client
from glanceclient import client as glance_client
from keystoneauth1 import session
from keystoneauth1.identity.v3 import ApplicationCredential
from keystoneclient import client as keystone_client
from nectarallocationclient import client as allocation_client
from novaclient import client as nova_client

from django.conf import settings
from django.utils.crypto import get_random_string

from vm_manager.constants import LINUX


class Nectar(object):
    """Nectar

    Class for encapsulating Nectar OpenStack clients and their
    authentication and includes some custom methods for complex
    queries.

    :Attributes:
        * **nova** - :class:`novaclient.client.Client`
        * **allocation** - `nectarallocationclient v1`_
        * **keystone** - :class:`keystoneclient.client.Client`
        * **glance** - :class:`glanceclient.client.Client`
        * **cinder** - :class:`cinderclient.client.Client`
        * **roles** - A list of roles (names) scoped to the authenticated
          user and project.

    .. todo:: Optionally construct object using parameters rather than
              loading environment variables.
    """

    def __init__(self):
        auth = ApplicationCredential(
            auth_url=settings.OS_AUTH_URL,
            application_credential_secret=
                settings.OS_APPLICATION_CREDENTIAL_SECRET,
            application_credential_id=settings.OS_APPLICATION_CREDENTIAL_ID)
        sess = session.Session(auth=auth)

        # Roles
        auth_ref = auth.get_auth_ref(sess)
        self.roles = auth_ref.role_names

        # Establish clients
        self.nova = nova_client.Client('2', session=sess)
        self.allocation = allocation_client.Client('1', session=sess)
        self.keystone = keystone_client.Client('3', session=sess)
        self.glance = glance_client.Client('2', session=sess)
        self.cinder = cinder_client.Client('3', session=sess)

        net_id = self.nova.neutron.find_network(settings.OS_NETWORK).id
        self.VM_PARAMS = {
            "metadata_volume": {'readonly': 'False'},
            "block_device_mapping": [{
                'source_type': "volume",
                'destination_type': 'volume',
                'delete_on_termination': False,
                'uuid': None,
                'boot_index': '0',
            }],
            "id_net": net_id,
            "list_net": [{'net-id': net_id}],
        }


def get_nectar():
    if not hasattr(get_nectar, 'nectar'):
        get_nectar.nectar = Nectar()
    return get_nectar.nectar


def generate_server_name(username, operating_system):
    return f"{operating_system}_{username}_{settings.ENVIRONMENT_NAME[0]}"


def generate_hostname_url(hostname_id, operating_system) -> str:
    return f"{generate_hostname(hostname_id, operating_system)}"


def generate_hostname(hostname_id, operating_system) -> str:
    return f"rd{operating_system[0]}-{hostname_id}"


def get_domain(user) -> str:
    return 'test'


class FlavorDetails(object):

    def __init__(self, flavor):
        self.id = flavor.id
        self.name = flavor.name
        self.ram = int(flavor.ram) / 1024
        self.disk = flavor.disk
        self.vcpus = flavor.vcpus


def after_time(seconds):
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def generate_password() -> str:
    return get_random_string(20)
