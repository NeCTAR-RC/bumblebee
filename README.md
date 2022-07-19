# Bumblebee

Bumblebee is a Django-based project designed to provide a simple interface for
users to be able to spin-up HTML5 virtual desktops for research workflows.

This code is developed by the Australian Research Data Commons (ARDC) from
the Researcher Desktop project developed by the University of Melbourne.

## Preliminary info

Bumblebee relies on OpenStack Keystone, Nova and Cinder to carry out its
VM-related activites. Setting up of an OpenStack environment is beyond the
scope of this humble README but we invite users to evaluate one of the
deployment projects. Docs for those are available for example for the Yoga
release [here](https://docs.openstack.org/yoga/deploy/). Please use the linked
webpage to navigate to the current release as needed.

Bumblebee uses Guacamole to connect to remote virtual desktops. Guacamole has to
have access to the instance network to connect to it via RDP. Thus, all of
routing, security groups and firewall settings must allow this. The instance's
image has to have RDP installed and set up to launch at boot. Bumblebee does not
enable config drive so the instance's network requires DHCP. Bumblebee sets up
a phone-home call via cloud-init and thus the instance must be allowed to call
Bumblebee's endpoint (again, ensure all relevant bits make it possible).

Guacamole *must* use Bumblebee's database as Bumblebee manages the Guacamole's
tables.

An OpenID Connect (OIDC) Identity Provider (OP), such as
[Keycloak](https://www.keycloak.org/)
is required for Bumblebee and Guacamole. It has to be presented under the same
name/address to both the client (browser) and the server parts for the authN
and authZ to succeed.

## Quick start

First, please read the preliminaries as they are very important!

The quickest way to start is to use the provided docker-compose file ready for
development and evaluation (testing) activities. It sets up Bumblebee,
Guacamole and Keycloak:

```shell
cp env-template .env
# read the .env file thoroughly and modify it properly
docker-compose up -d
# set up Keycloak
# modify the .env file
docker-compose up -d
```

Currently, Keycloak has to be set up manually. The admin/admin user can be
used for that purpose. Any valid realm may be created and its details put
in the ``.env`` file afterwards with a final run of docker-compose to get
Bumblebee working with it. Both Bumblebee and Guacamole need their own
clients set up in Keycloak to work with it.
