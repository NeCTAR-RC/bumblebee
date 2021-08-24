from researcher_workspace.settings import NOTIFY_URL
from researcher_desktop.constants import NOTIFY_VM_PATH_PLACEHOLDER
from vm_manager.constants import SCRIPT_ERROR, SCRIPT_OKAY, CLOUD_INIT_FINISHED, CLOUD_INIT_STARTED,\
    HOSTNAME_URL_PLACEHOLDER, HOSTNAME_PLACEHOLDER


user_data_ubuntu = f"""#!/bin/bash
# set standard hostname like rdl-123456.desktop.cloud.unimelb.edu.au
IP=`/sbin/ip addr show eth0 | grep inet | grep -v inet6 | awk -F'inet' '{{print $2}}' | awk '{{print $1}}' | cut -f1 -d'/'`
HN_URL="{HOSTNAME_URL_PLACEHOLDER}"
HN="{HOSTNAME_PLACEHOLDER}"
hostnamectl set-hostname $HN_URL

echo "$IP $HN_URL $HN" >> "/etc/hosts"

curl -o - "{NOTIFY_URL}{NOTIFY_VM_PATH_PLACEHOLDER}?ip=$IP&hn=$HN&state={SCRIPT_OKAY}&os=linux&msg={CLOUD_INIT_STARTED}"

lsblk | grep vdb > /dev/null
if [ $? -eq 0 ]; then
    mv /home/ubuntu /var/lib/
    usermod -d /var/lib/ubuntu ubuntu
    mkfs.ext4 /dev/vdb && cat >> /etc/fstab  <<_EOF
/dev/vdb /home      ext4    errors=remount-ro   0    2
_EOF
    mount /home
fi

echo 'ubuntu:Nectar1!' | chpasswd

# CURL to the VM-Manager to confirm that the instance is ready for use
curl -o - "{NOTIFY_URL}{NOTIFY_VM_PATH_PLACEHOLDER}?ip=$IP&hn=$HN&state={SCRIPT_OKAY}&os=linux&msg={CLOUD_INIT_FINISHED}"
"""
