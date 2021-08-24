from researcher_workspace.models import Feature
from specialty_resources.constants import BASIC_FLAVORS, IMAGE_NAME, APP_NAME
from vm_manager.utils.utils import get_nectar


class VMInfo(object):
    def __init__(self):
        n = get_nectar()
        flavor_list = n.nova.flavors.list()
        self.FLAVORS = {}
        for flavor, flavor_val in BASIC_FLAVORS.items():
            self.FLAVORS[flavor] = find_flavor(flavor_list, flavor_val)
        self.SOURCE_VOLUME = {}
        for operating_system in IMAGE_NAME.keys():
            self.SOURCE_VOLUME[operating_system] = \
                n.cinder.volumes.list(search_opts={'name': IMAGE_NAME[operating_system]})[0].id
        self.FEATURE = Feature.objects.get(app_name=APP_NAME)


def get_vm_info():
    if not hasattr(get_vm_info, 'vm_info'):
        get_vm_info.vm_info = VMInfo()
    return get_vm_info.vm_info


def find_flavor(flavor_list, flavor_name):
    for flavor in flavor_list:
        if flavor_name in flavor.name:
            return flavor.id
    raise Exception('Could not find flavor: ' + flavor_name)
