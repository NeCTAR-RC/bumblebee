# Copy this file to make your own local_settings.py

### DJANGO Settings ### 

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Django Security Settings
# SECURITY RECOMMENDATION: Set the following to False for dev env!
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = ""  # ¡Change!

# For test/prod server environment (comment out the developer version)
# ALLOWED_HOSTS = ['<Fully Qualified Domain Name>']

# For development environment (comment out the server version)
# ALLOWED_HOSTS = ['localhost', '<tunnel ip>']

# For server setup you should set this
# STATIC_ROOT = <path to static root>

# List of people who are emailed when web app encounters an error
ADMINS = ""  # ¡Change!

### OpenStack Settings ###

# OpenStack credentials to use for this application
# See:
# > openstack application credential create <name>
# > openstack application credential list
OS_APPLICATION_CREDENTIAL_ID = ""  # ¡Change!
OS_APPLICATION_CREDENTIAL_SECRET = ""  # ¡Change!

# OpenStack Key you have access
OS_KEYNAME = ""  # ¡Change!
OS_NETWORK = ""  # ¡Change!
OS_SECGROUPS = []  # ¡Change!

# Type of desktop console server that is used by the Guacamole server:
# 'openstack_hypervisor' uses the builtin VNC server of the OpenStack hypervisor
# 'instance_builtin' uses an RDP server running within a created OpenStack desktop instance
OS_CONSOLE_SERVER = 'instance_builtin'

### Researcher Desktop Settings

# Banner label on site only visible by users with is_superuser=True
ENVIRONMENT_NAME = ""  # ¡Change!
ENVIRONMENT_COLOR = ""  # ¡Change!

# End-point for launching desktops to tell the server success/error
# Base url only: e.g. http://<server>:<port>
NOTIFY_URL = ""  # ¡Change!

# Base URL for this site, used by Invite-link functionality as the prefix to links
# Base url only: e.g. http://<server>:<port>
SITE_URL = ""  # ¡Change!

# The URL for the Guacamole server
# e.g https://<server>/guacamole
GUACAMOLE_URL = ""  # ¡Change!

# Details of the "bootstrap" desktop types.  These are used to populate
# table in the bootstrap migration.  After that, the desktop types can
# be modified via the database; e.g. using the Django admin UI, or via
# a (hypothetical) REST API.
# DESKTOP_TYPES = [
#    {
#        'name': "linux",
#        'image_name': "<glance image name>",
#        'description': "Generic Linux",
#        'default_flavor_name': "<flavor_name>",
#        'big_flavor_name': "<flavor_name>",
#        'volume_size': "<size_in_GB>",
#        'logo': "<a_url>",
#        'details': { ... }    # JSON
#    },
#]

# MySQL backend settings
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': '<db_name>',
#         'USER': '<username>',
#         'PASSWORD': '<password>',
#         'HOST': '<host>',
#         'PORT': '5432',
#     }
# }

GENERAL_WARNING_MESSAGE = "A message you want all logged in users to see, for instance " \
                          "a warning about an upcoming deployment outage"

# Set to True to use the settings specific to Test Cloud
TEST_CLOUD = False

# Settings specific to Test Cloud

if TEST_CLOUD:
# DESKTOP_TYPES = [
#    {
#        'name': "linux",
#        'image_name': "<glance image name>",
#        'description': "Generic Linux",
#        'default_flavor_name': "<flavor_name>",
#        'big_flavor_name': "<flavor_name>"
#    },
#]

    ENVIRONMENT_NAME = ""
    ENVIRONMENT_COLOR = "#2eb67d"

    # test cloud app cred
    OS_APPLICATION_CREDENTIAL_ID = ''
    OS_APPLICATION_CREDENTIAL_SECRET = ''

    # Also remember to change the keystone authentication in settings.
    OS_AUTH_URL = "https://keystone.test.rc.nectar.org.au:5000/v3/"

    OS_AVAILABILITY_ZONE = ''
    OS_NETWORK = ''

    OIDC_SERVER_URL = 'https://sso.test.rc.nectar.org.au/auth/realms/nectar/protocol/openid-connect'
    OIDC_RP_CLIENT_ID = ''
    OIDC_RP_CLIENT_SECRET = ''
