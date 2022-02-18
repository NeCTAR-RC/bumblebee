"""
Django settings for bumblebee project.

For more information on this file, see
https://docs.djangoproject.com/en/2.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.2/ref/settings/
"""

import os
import logging

from django.contrib.messages import constants as message_constants
from django.contrib.messages import constants as messages

from django.urls import reverse_lazy

NAME = 'Bumblebee'

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.2/howto/deployment/checklist/

ADMINS = [('Andy', 'andy@example.com'),
          ('Stephen', 'stephen@example.com')]

MANAGERS = ADMINS

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ['localhost']

# Application definition

INSTALLED_APPS = [
    'vm_manager.apps.VmManagerConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'mozilla_django_oidc',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'compressor',
    'guacamole',
    'researcher_workspace',
    'mathfilters',
#    'django_rq',
    'researcher_desktop',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django_currentuser.middleware.ThreadLocalUserMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'researcher_workspace.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'researcher_workspace', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'researcher_workspace.context_processors.from_settings',

            ],
        },
    },
]

WSGI_APPLICATION = 'researcher_workspace.wsgi.application'

# Django Security settings
# https://docs.djangoproject.com/en/3.0/topics/security/
# https://dev.to/coderasha/django-web-security-checklist-before-deployment-secure-your-django-app-4jb8

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'

# Database
# https://docs.djangoproject.com/en/2.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'researcher_workspace.auth.NectarAuthBackend',
]

AUTH_USER_MODEL = 'researcher_workspace.User'

# OpenID Connect Auth settings
OIDC_SERVER_URL = 'https://sso.example.com/'
OIDC_RP_CLIENT_ID = 'bumblebee'
OIDC_RP_SIGN_ALGO = 'RS256'
OIDC_OP_AUTHORIZATION_ENDPOINT = f'{OIDC_SERVER_URL}/auth'
OIDC_OP_TOKEN_ENDPOINT = f'{OIDC_SERVER_URL}/token'
OIDC_OP_USER_ENDPOINT = f'{OIDC_SERVER_URL}/userinfo'
OIDC_OP_JWKS_ENDPOINT = f'{OIDC_SERVER_URL}/certs'


OIDC_USERNAME_ALGO = 'researcher_workspace.auth.generate_username'



# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Australia/Melbourne'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = 'static'

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
)

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "researcher_workspace/static"),
]

COMPRESS_PRECOMPILERS = (
    ('text/x-scss', 'django_libsass.SassCompiler'),
)

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

LOGIN_REDIRECT_URL = reverse_lazy('home')
LOGOUT_REDIRECT_URL = reverse_lazy('index')
LOGIN_REDIRECT_URL_FAILURE = reverse_lazy('login_fail')

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

OS_AUTH_URL = "https://keystone.rc.nectar.org.au:5000/v3/"
OS_AUTH_TYPE = 'v3applicationcredential'
OS_AVAILABILITY_ZONE = 'some-az'
OS_NETWORK = 'bumblebee'
OS_SECGROUPS = ['bumblebee']

# See:
# http://www.webforefront.com/django/setupdjangologging.html
# https://www.caktusgroup.com/blog/2015/01/27/Django-Logging-Configuration-logging_config-default-settings-logger/
# https://docs.djangoproject.com/en/2.2/topics/logging/

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'formatters': {
        'simple': {
            'format': '[%(asctime)s] %(levelname)s %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'verbose': {
            'format': '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'log_file': {
            'level': 'DEBUG',
            'filters': ['require_debug_false'],
            'class': 'logging.FileHandler',
            'filename': 'dashboard_app.log',
            'formatter': 'verbose'
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
            'include_html': True,
            'reporter_class': 'researcher_workspace.utils.custom_exception_reporter.CustomExceptionReporter',
        },
    },
    'loggers': {
        # root logger...
        '': {
            'handlers': ['console', 'log_file', 'mail_admins'],
        },
        'researcher_workspace': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'vm_manager': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'mozilla_django_oidc': {
            'handlers': ['console'],
            'level': 'DEBUG'
        },
    }
}

# The following is the default message level that will be shown to users.
# NB: for debug messages to show (by default they are not shown), add
#   from django.contrib.messages import constants as message_constants
#   MESSAGE_LEVEL = message_constants.DEBUG
# to the local_settings.py
MESSAGE_LEVEL = message_constants.INFO

# The following maps the message classes to the UoM css classes defined at:
#   https://web.unimelb.edu.au/components/notices/
MESSAGE_TAGS = {
    messages.INFO: 'notice--info',
    messages.SUCCESS: 'notice--success',
    messages.WARNING: 'notice--warning',
    messages.ERROR: 'notice--danger',
}

# https://docs.djangoproject.com/en/2.2/ref/settings/#internal-ips
# must be set to localhost if we want to use 'debug' in templates...
INTERNAL_IPS = "127.0.0.1"

# Freshdesk details for ticket interactions and / or email outbounding
FRESHDESK_DOMAIN = "nectar.org.au"
FRESHDESK_KEY = "secret"
FRESHDESK_GROUP_ID = 1
FRESHDESK_EMAIL_CONFIG_ID = 123

USER_LIMIT = 350  # 200 researchers + 25 support staff + 25 non-valid users we've got so far

# The page that users are redirected to after using invitation token
NEXT_PAGE = '/home'

# Empty warning message, should be filled in local_settings
GENERAL_WARNING_MESSAGE = ""

# Current version number for the terms and conditions
TERMS_VERSION = 1

# Users are limited to this number of workspaces.  Use zero for unlimited
LIMIT_WORKSPACES_PER_USER = 1

# If True, requests for new workspaces will be auto-approved
AUTO_APPROVE_WORKSPACES = True

# A list of Features that are permitted by default when a Workspace
# is approved.  (A list of the Feature 'app_name' values.)
PROJECT_DEFAULT_FEATURES = ['researcher_desktop']

# Expiry policy constants.  Units are days
BOOST_EXPIRY = 7
BOOST_EXTENSION = 7
BOOST_LIFETIME = 14
INSTANCE_EXPIRY = 14
INSTANCE_EXTENSION = 14
INSTANCE_LIFETIME = -1
SHELVED_VOLUME_EXPIRY = 90

# Values that need to be set in local_settings.py
PROXY_URL = False
SECRET_KEY = 'secret'
OS_APPLICATION_CREDENTIAL_ID = 'os_cred_id'
OS_APPLICATION_CREDENTIAL_SECRET = 'os_cred_secret'

OS_KEYNAME = 'os_keyname'
ENVIRONMENT_NAME = 'tiger'
ENVIRONMENT_COLOR = 'pink'
NOTIFY_URL = 'http://notify'
SITE_URL = 'http://site'
GUACAMOLE_URL = 'http://guacamole'
ALLOCATION_ID = '12345'

logger = logging.getLogger(__name__)

RQ_QUEUES = {
    'default': {
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 0,
        'DEFAULT_TIMEOUT': 360,
    },
}

DESKTOP_TYPES = [
    {
        'id': "ubuntu",
        'image_name': "NeCTAR Ubuntu 20.04 LTS (Focal) Virtual Desktop",
        'name': "Generic Linux (Ubuntu)",
        'description': "Better than sliced bread",
        'default_flavor_name': "m3.medium",
        'big_flavor_name': "m3.xxlarge"
    },
    {
        'id': "centos",
        'image_name': "NeCTAR Ubuntu 20.04 LTS (Focal) Virtual Desktop",
        'name': "CentOS 7",
        'description': "Sliced bread",
        'default_flavor_name': "m3.medium",
        'big_flavor_name': "m3.xxlarge"
    },
    {
        'id': "tern",
        'image_name': "NeCTAR Ubuntu 20.04 LTS (Focal) Virtual Desktop",
        'name': "TERN / CoESRA Desktop",
        'description': "A kind of bird",
        'default_flavor_name': "m3.medium",
        'big_flavor_name': "m3.xxlarge",
        'restrict_to_zones': ["QRIScloud"]
    },
]

ZONES = [
    {
        'name': "QRIScloud",
        'zone_weight': 10,
        'domains': ['uq.edu.au', 'qut.edu.au']
    },
    {
        'name': "melbourne-qh2",
        'zone_weight': 15,
        'domains': ['unimelb.edu.au']
    },
    {
        'name': "monash-01",
        'zone_weight': 20,
        'domains': ['monash.edu']
    },
]
