from cinderclient import client as cinder_client
from glanceclient import client as glance_client
from keystoneauth1 import session
from keystoneauth1.identity.v3 import ApplicationCredential
from keystoneclient import client as keystone_client
from nectarallocationclient import client as allocation_client
from novaclient import client as nova_client

from django.conf import settings

#from researcher_workspace.resplat.ldap_backend import ResplatLDAPBackend
from researcher_workspace.settings import ENVIRONMENT_NAME
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

    .. _`nectarallocationclient v1` : https://github.com/NeCTAR-RC/python-necta
                                      rallocationclient/tree/master/nectaralloc
                                      ationclient/v1
    """

    def __init__(self):
        auth = ApplicationCredential(
            auth_url=settings.OS_AUTH_URL,
            application_credential_secret=settings.OS_APPLICATION_CREDENTIAL_SECRET,
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

        self.VM_PARAMS = {
            "metadata_volume": {'readonly': 'False'},
            "availability_zone_volume": settings.OS_AVAILABILITY_ZONE,
            "size": 20,
            "block_device_mapping": [{
                'source_type': "volume",
                'destination_type': 'volume',
                'delete_on_termination': False,
                'uuid': None,
                'boot_index': '0',
                'volume_size': 20,
            }],
            "availability_zone_server": settings.OS_AVAILABILITY_ZONE,
            "id_net": self.nova.neutron.find_network(settings.OS_NETWORK).id,
            "list_net": [{
                'net-id': self.nova.neutron.find_network(settings.OS_NETWORK).id
            }],
        }
        #self.VM_PARAMS["block_device_mapping"][0]["volume_size"] = self.VM_PARAMS["size"]
        #self.VM_PARAMS["list_net"] = [{'net-id': self.VM_PARAMS["id_net"]}]


def get_nectar():
    if not hasattr(get_nectar, 'nectar'):
        get_nectar.nectar = Nectar()
    return get_nectar.nectar


def generate_server_name(username, operating_system):
    return f"{operating_system}_{username}_{ENVIRONMENT_NAME[0]}"


def generate_hostname_url(hostname_id, operating_system) -> str:
    return f"{generate_hostname(hostname_id, operating_system)}.desktop.cloud.unimelb.edu.au"


def generate_hostname(hostname_id, operating_system) -> str:
    return f"rd{operating_system[0]}-{hostname_id}"


def get_domain(user) -> str:
    #backend = ResplatLDAPBackend()
    #if 'student' in backend.get_user(user.id).ldap_user.attrs['auedupersontype']:
    #    return STUDENT
    return 'test'
