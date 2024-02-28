#!/bin/sh

#
# This script is used to import a demo Desktop image (Ubuntu jammy) into 
# OpenStack and then create a bootable volume snapshot usable by Bumblebee
#
# You may need to modify this to suit your environment.
#
# It can take some time for both the image and volume to reach the
# available stage, so be patient :)
#

# Modify to your OpenStack setup
AZ=nova

NAME="Ubuntu 22.04 LTS (Jammy) Virtual Desktop [1]"
DEMO_IMAGE=https://swift.rc.nectar.org.au/v1/AUTH_2f6f7e75fc0f453d9c127b490b02e9e3/bumblebee/bumblebee-demo-jammy-virtual-desktop-v1.img

IMAGE_ID=$(openstack image list -c ID -f value --name "$NAME")
if [ -z "$IMAGE_ID" ]; then
    echo "Downloading demo image..."
    curl -C - -L -o bumblebee-demo.img "$DEMO_IMAGE"

    echo "Creating image..."
    IMAGE_ID=$(openstack image create -c id -f value --disk-format qcow2 --container-format bare \
        --property default_user='ubuntu' --property os_distro='ubuntu' --property os_version='22.04' --property hw_qemu_guest_agent='True' \
        --file "bumblebee-demo.img" "$NAME")
    rm -f bumblebee-demo.img
    echo "Image ID: $IMAGE_ID"
else
    echo "Found existing image: $IMAGE_ID"
fi

VOLUME_ID=$(openstack volume list -c ID -f value --name "$NAME")
if [ -z "$VOLUME_ID" ]; then
    echo "Creating volume..."
    VOLUME_ID=$(openstack volume create -c id -f value --size 30 --image $IMAGE_ID \
        --availability-zone $AZ "$NAME")
    echo "Volume ID: $VOLUME_ID"
else
    echo "Found existing volume: $VOLUME_ID"
fi
