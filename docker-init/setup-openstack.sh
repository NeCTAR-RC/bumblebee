#!/bin/sh

#
# This script creates an OpenStack application credential for Bumblebee
# to be able to talk to the OpenStack APIs. 
#
# It also creates a security group and rules for virtual desktops, which
# allows ICMP, SSH and RDP from the Guacamole server.
#
# The app cred ID/token should be added to your .env file for Bumblebee
#
# Adjust the CIDR to allow access from your Guacamole servers!
#

CIDR="172.16.0.0/12"

# Application credential to go into .env
openstack application credential create --role Member bumblebee

# Security group setup
openstack security group create bumblebee-desktops
openstack security group rule create --proto icmp bumblebee-desktops
openstack security group rule create --remote-ip $CIDR --proto tcp --dst-port 22 bumblebee-desktops
openstack security group rule create --remote-ip $CIDR --proto tcp --dst-port 3389 bumblebee-desktops
