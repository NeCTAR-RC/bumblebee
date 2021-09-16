from researcher_desktop.constants import APP_NAME
from researcher_desktop.models import DesktopType
from researcher_workspace.models import Feature
from vm_manager.utils.utils import get_nectar


class VMInfo(object):
    def __init__(self):
        n = get_nectar()
        flavor_list = n.nova.flavors.list()
        self.DEFAULT_FLAVOR = find_flavor(flavor_list, DEFAULT_FLAVOR)
        self.BIG_FLAVOR = find_flavor(flavor_list, BIG_FLAVOR)
        self.SOURCE_VOLUME = {}
        for dt in DesktopType.objects.all():
            self.SOURCE_VOLUME[dt.name] = \
                n.cinder.volumes.list(
                    search_opts={'name': dt.image_name})[0].id
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


def desktop_type_names():
    return DesktopType.objects.values_list('name', flat=True)
