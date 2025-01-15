# Bumblebee

Bumblebee is a Django-based project designed to provide a simple interface for
users to be able to spin-up HTML5 virtual desktops for research workflows on
OpenStack.

This code is developed by the Australian Research Data Commons (ARDC) from
the Researcher Desktop project developed by the University of Melbourne.


## Features

The Bumblebee project was designed with several goals in mind, so some of the
features that have been implemented are:

* Authentication via OpenID connect
* Multi Availablity Zone support
* Desktops available via the browser for ease of use
* Desktops provisioned on a private network with no allowed incoming
  external connections, for security reasons
* Drag and drop file transfer support
* Audio redirection
* Configurable time limits and reminder notifications
* Boost support for temporarily resizing a desktop to a larger flavor
* Linux support, but Windows support is planned in a future release (Q4 2023)


## How it works

The architecture of a working Bumblebee installation is compromised of two
distinct components; the Bumblebee web service (and related services) and
the Guacamole component.

For our production system, the Bumblebee web app component runs in a
Kubernetes cluster, deployed with a Helm chart. The Guacamole component is
deployed onto a cluster of OpenStack VMs in each of the OpenStack availability
zones we support. We do this via a Heat stack with an Octavia Load Balancer.

The Bumblebee web service provides the front door for users, where they can
create an initial *workspace* by providing some information about their
use-case.

Once their workspace has been approved, users are then able to browse a
catalogue of available desktop environments, each with some basic information
about its features.

Once a desktop environment has been chosen, users can launch a desktop, with
their choice of Availability Zone, if more than one is available.

At this point, Bumblebee calls the OpenStack APIs to first clone the *volume*
of the chosen desktop environment. Once that volume is ready, it then calls
the APIs again to provision an OpenStack server with the newly created volume
as its boot source.

The server is also provided with user-data which cloud-init will use for
preparing the desktop and set things like the user's timezone and the user
account's RDP randomly generated password.

Bumblebee will wait for the instance to become active and then expect the
instance to phone home (callback) to indicate the boot was successful.

Users are then presented with an *Open Desktop* button for their desktop,
which directs the user to the Guacamole server which then provides the virtual
desktop interface directly in the browser.

Internally, Bumblebee creates Guacamole connection records with its database
directly which includes the RDP connection settings (e.g. IP address, username,
password, etc) and Guacamole essentially acts as a proxy to RDP that is
pre-configured and running in the desktop environment.

Users are then able to manage their desktop environment, with functions
including delete, reboot (soft, hard) and boost. Boost allows users to jump
to an OpenStack flavor with more resource if needed, via an OpenStack
server resize.

Bumblebee has some asynchronous jobs that run at set intervals, which can be
used for time-limiting users desktops if required. In this case, users are
sent reminder and confirmation notifications through the process of renewing
and expiring of their desktop.


## Supporting projects

In conjunction with this repository, there are several other related
repositories that make up the broader Bumblebee ecosystem.

* [bumblebee-images](https://github.com/NeCTAR-RC/bumblebee-images) for
building Bumblebee compatible images with Packer and Ansible.
* [bumblebee-helm](https://github.com/NeCTAR-RC/bumblebee-helm) for deploying
the Bumblebee web app on Kubernetes.


## Requirements

Python and Django versions:  While we try to support at or near the latest
Django version, we may fall behind.  (Our main priority is support something
that is compatible with Nectar's production environment.)

* Python 3.10 or later and Django 5.0.x are recommended (on Ubuntu Jammy).
  Python 3.10 + Django 5.0.x is our dev and CI test target.
* If you are using Python 3.8, Django 4.2.x should work but we don't support
  them anymore.
* Earlier versions of Django are end-of-life.

Bumblebee relies on OpenStack Keystone, Nova, Cinder and Neutron to carry out its
VM-related activites. Setting up of an OpenStack environment is beyond the
scope of this humble README but we invite users to evaluate one of the
deployment projects. Docs for those are available for example for the Yoga
release [here](https://docs.openstack.org/yoga/deploy/). Please use the linked
webpage to navigate to the current release as needed.

Bumblebee expects to have a set of OpenStack application credentials set for
interacting with the OpenStack APIs. When launching desktops, it will look for
a volume with a given name and provision a clone of it, which is then used as
the boot source for a VM instance, provisioned on a defined private network.

Bumblebee uses Guacamole to connect to remote virtual desktops. Guacamole has to
have access to the instance network to connect to it via RDP port 3389.
Thus, all of routing, security groups and firewall settings must allow this.

The instance's image has to have RDP installed and configured to launch at
boot. Bumblebee does not enable config drive so the instance's network
requires DHCP. Bumblebee sets up a phone-home call via cloud-init and thus
the instance must be allowed to call Bumblebee's endpoint (again, ensure all
relevant bits make it possible).

Guacamole *must* use Bumblebee's database as Bumblebee manages the Guacamole's
tables at this stage.

An OpenID Connect (OIDC) Identity Provider (OP), such as
[Keycloak](https://www.keycloak.org/)
is required for Bumblebee and Guacamole. It has to be presented under the same
name/address to both the client (browser) and the server parts for the authN
and authZ to succeed.

(There is a non-OIDC mode that is used for testing.  This is enabled by passing
the USE_OIDC=False environment variable to the bumblebee server.  However this
is not suitable for general production use.  One reason is that only 'staff'
accounts are able to login via the login form.)

## Quick start

First, please read the preliminaries as they are very important!

The quickest way to start is to use the provided docker-compose file ready for
development and evaluation (testing) activities. It sets up Bumblebee,
Guacamole, MariaDB, Redis and Keycloak:

```shell
cp env-template .env
# read the .env file thoroughly and modify it properly
docker-compose up -d
```

The env-template does provide most settings which will work for this
docker-compose environment, but you will have to provide your own OpenStack
cloud for testing Virtual Desktop creation.

The Keycloak instance is set up automatically to provide an default bumblebee
realm, with the following default users for testing Bumblebee:

  - Admin user with the `admin` role:
    * Username: admin
    * Password: password
  - Unprivileged user with no additional roles:
    * Username: user
    * Password: password

The Keycloak instance can be accessed with the admin/admin user to configure
further OpenID Connect settings if needed. Both Bumblebee and Guacamole need
their own OpenID Connect client endpoints to request authentication of a user.
Therefore, the Keycloak instance provides two OpenID Connect clients
configured properly.

A successful docker-compose test setup with a proper authentication only works
if your Docker host machine can resolve the names of all Docker services. The
name resolution can be implemented by using a DNS proxy server or by adding the
following line to the `/etc/hosts` file of the Docker host machine:

```
127.0.0.1  bumblebee keycloak guacamole
```

Then you can access the running Bumblebee service from your Docker host machine
under the following URL:

```
http://bumblebee:8000
```

### OpenStack configuration

When trying out Bumblebee, you will need to bring your own OpenStack
installation. We have not yet tested against DevStack, but it should work.

When setting up the OpenStack requirements Bumblebee, you will need:
  - Application Credentials for the project
  - A network ID for each Availability Zone
  - A bootable volume for each desktop environment available to users

We provide some helper scripts in the `docker-init` directory which can help
set these up. You may need to modify them to suit your environment though.

The scripts available and their functions are:
  - setup-openstack.sh
    * creates OpenStack application credentials
    * creates desktop security group and adds rules that allow ICMP, SSH and
      RDP
  - setup-volume.sh
    * Downloads a demo Ubuntu 22.04 (jammy) Virtual Desktop image
    * Uploads the image into your OpenStack image service
    * Creates a 30GB bootable volume from that image
  - setup-desktop-type.sh
    * Creates the initial Desktop Type object based on the demo image

Once you have done this step, you need to log into Bumblebee (as the admin
user) and in the **ADMIN** portal and create your Availability Zone. This
should represent your OpenStack Availability Zone.

You also need to create your initial Desktop Type with the
`setup-desktop-type.sh` mentioned earlier. You may need to modify the
`docker-init/initial_desktop-type.yaml` file if your OpenStack compute
flavors are not `m1.small` and `m1.medium`, but running that script
should create the initial config for you.

At this point, you could try and boot yourself a Virtual Desktop. It is a
complicated setup with many moving parts, so if you get stuck, please reach
out.

**NOTE**: If you're running on Docker and using an external OpenStack cloud,
then you'll find that the phone home process won't work, as the desktop won't
be able to resolve the `bumblebee` hosts entry we created locally.

We don't really have a solution for that just yet, but you can manually
set the VMStatus object of your Virtual Desktop in the admin interface
to `VM_Okay`, and Bumblebee will think it's fine.


## Selenium tests

(This section covers the selenium UI tests in the Bumblebee codebase.
There are more extensive tests in the bumblebee-stormbee project that are
designed to be run as "tempest" style tests against Nectar's production
and test installations.)

These selenium tests are intended to be run in a fully configured bumblebee
development environment with the redis service, rqscheduler and rqworker
already running.  You will need to install Firefox and some additional
dependencies.

-  On a machine with a graphics, just install regular firefox.

```
sudo apt-get install firefox
```

- On a headless machine, you need the non-Snap version of firefox.  See
https://www.omgubuntu.co.uk/2022/04/how-to-install-firefox-deb-apt-ubuntu-22-04 for instructions on how to install it.  Then you need to install
the following.

```
sudo apt-get install xvfb libxi6 libgconf-2-4
```

Before running tests, you will need to start a virtual framebuffer as
follows.  (NB: The X11 ports 6000-6063 should not be open for security
reasons.  The "-ac" option is disabling host access control; see the
Xserver(1) manual entry.)

```
sudo Xvfb :5 -ac &
export DISPLAY=:5
```

If necessary, create a writeable directory where the automated Firefox
can create user profiles; e.g.

```
mkdir /home/ubuntu/bumblebee/tmp
export TMPDIR=/home/ubuntu/bumblebee/tmp
```

If you have a Github API token, export it as an environment variable.
This will avoid problems with Github API rate limiting if you run the
selenium tests repeatedly from the same machine.

```
export GH_TOKEN=...    # This is optional ...
```

Finally, to run the tests:

```
tox -e selenium
```

The tests will use a selenium driver manager to download a compatible
chromedriver for your installed Firefox.  The driver will be cached
for a day.

When you are done, you can kill the Xvfb process.

