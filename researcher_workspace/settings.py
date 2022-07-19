"""
Django settings for bumblebee project.

For more information on this file, see
https://docs.djangoproject.com/en/2.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.2/ref/settings/
"""

import logging
import os

from distutils.util import strtobool

from django.contrib.messages import constants as message_constants
from django.contrib.messages import constants as messages

from django.urls import reverse_lazy

from researcher_workspace.utils import secret_key

# Stuff can happen from this point that is useful for deployer, need to get a
# logger now
logger = logging.getLogger(__name__)


def get_setting(setting, default=None, required=False):
    value = os.environ.get(setting, default)
    if required and not value:
        logger.info('Setting value for %s not found!', setting)
    return value

NAME = 'ARDC Nectar Virtual Desktop'

# Image tag of the running container environment
IMAGE_ID = get_setting('IMAGE_ID', 'unknown')

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.2/howto/deployment/checklist/

ADMINS = [
    ('Andy', 'andy.botting@ardc.edu.au'),
    ('Stephen', 'stephen.crawley@ardc.edu.au')
]

MANAGERS = ADMINS

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = bool(strtobool(get_setting('DEBUG', 'False')))

ALLOWED_HOSTS = get_setting('ALLOWED_HOSTS', 'localhost').split(',')

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
    'django.contrib.humanize',
    'compressor',
    'guacamole',
    'researcher_workspace',
    'mathfilters',
    'django_rq',
    'researcher_desktop',
    'health_check',
    'health_check.db',
    'health_check.cache',
    'health_check.contrib.migrations',
    'health_check.contrib.redis',
    'django_prometheus',
]

MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django_currentuser.middleware.ThreadLocalUserMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'researcher_workspace.middleware.TimezoneMiddleware',
    'researcher_workspace.middleware.MetricsAuthMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
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
X_FRAME_OPTIONS = 'DENY'

# Database
# https://docs.djangoproject.com/en/2.2/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': get_setting('DB_ENGINE', 'django.db.backends.mysql'),
        'NAME': get_setting('DB_NAME', 'bumblebee'),
        'USER': get_setting('DB_USER'),
        'PASSWORD': get_setting('DB_PASSWORD'),
        'HOST': get_setting('DB_HOST'),
        'PORT': get_setting('DB_PORT', '3306'),
    }
}

# Redis queue
REDIS_HOST = get_setting('REDIS_HOST', 'localhost')
REDIS_PORT = get_setting('REDIS_PORT', '6379')
REDIS_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}'
RQ_QUEUES = {
    'default': {
        'HOST': REDIS_HOST,
        'PORT': REDIS_PORT,
        'DB': 0,
        'DEFAULT_TIMEOUT': 360,
    },
}


# OpenStack config
OS_APPLICATION_CREDENTIAL_ID = get_setting('OS_APPLICATION_CREDENTIAL_ID')
OS_APPLICATION_CREDENTIAL_SECRET = get_setting('OS_APPLICATION_CREDENTIAL_SECRET')

OS_AUTH_URL = get_setting('OS_AUTH_URL')
OS_SECGROUPS = get_setting('OS_SECGROUPS', 'bumblebee').split(',')
OS_KEYNAME = get_setting('OS_KEYNAME')

OS_PROJECT_ID = get_setting('OS_PROJECT_ID', '')

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'researcher_workspace.auth.NectarAuthBackend',
]

AUTH_USER_MODEL = 'researcher_workspace.User'

# OpenID Connect Auth settings
OIDC_SERVER_URL = get_setting('OIDC_SERVER_URL')
OIDC_RP_CLIENT_ID = get_setting('OIDC_RP_CLIENT_ID', 'bumblebee')
OIDC_RP_SIGN_ALGO = 'RS256'
OIDC_USERNAME_ALGO = 'researcher_workspace.auth.generate_username'

# OIDC_RP_SCOPES should include a scope that serves the ``roles`` claim
# in the ID token, with an array of user's roles.
OIDC_RP_SCOPES = get_setting('OIDC_RP_SCOPES', 'openid email')

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Australia/Melbourne'
USE_I18N = True
USE_L10N = True
USE_TZ = True

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
)

# Static files (CSS, JavaScript, Images)
STATIC_ROOT = 'static'
STATIC_URL = '/static/'

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "researcher_workspace/static"),
]

COMPRESS_PRECOMPILERS = (
    ('text/x-scss', 'django_libsass.SassCompiler'),
)

LOGIN_REDIRECT_URL = reverse_lazy('home')
LOGOUT_REDIRECT_URL = reverse_lazy('index')
LOGIN_REDIRECT_URL_FAILURE = reverse_lazy('login_fail')

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# See:
# http://www.webforefront.com/django/setupdjangologging.html
# https://www.caktusgroup.com/blog/2015/01/27/Django-Logging-Configuration-logging_config-default-settings-logger/
# https://docs.djangoproject.com/en/2.2/topics/logging/

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
            'format': '[%(asctime)s] [%(levelname)s] %(message)s',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'console'
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'include_html': True,
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'researcher_workspace': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'vm_manager': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    }
}

# The following is the default message level that will be shown to users.
# NB: for debug messages to show (by default they are not shown), add
#   from django.contrib.messages import constants as message_constants
#   MESSAGE_LEVEL = message_constants.DEBUG
# to the local_settings.py
MESSAGE_LEVEL = message_constants.INFO

MESSAGE_TAGS = {
    messages.DEBUG: 'info',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}

# https://docs.djangoproject.com/en/2.2/ref/settings/#internal-ips
# must be set to localhost if we want to use 'debug' in templates...
INTERNAL_IPS = "127.0.0.1"

# The page that users are redirected to after using invitation token
NEXT_PAGE = '/home'

# Current version number for the terms and conditions
TERMS_VERSION = int(get_setting('TERMS_VERSION', 1))

# Users are limited to this number of workspaces.  Use zero for unlimited
LIMIT_WORKSPACES_PER_USER = int(get_setting('LIMIT_WORKSPACES_PER_USER', 1))

# If True, requests for new workspaces will be auto-approved
AUTO_APPROVE_WORKSPACES = bool(strtobool(
    get_setting('AUTO_APPROVE_WORKSPACES', 'True')))

# A list of Features that are permitted by default when a Workspace
# is approved.  (A list of the Feature 'app_name' values.)
PROJECT_DEFAULT_FEATURES = ['researcher_desktop']

DESKTOP_TYPES = get_setting('DESKTOP_TYPES')
ZONES = get_setting('ZONES')

GENERAL_WARNING_MESSAGE = get_setting('GENERAL_WARNING_MESSAGE')
# Friendly name for the current environment.
ENVIRONMENT_NAME = get_setting('ENVIRONMENT_NAME')
ENVIRONMENT_COLOR = get_setting('ENVIRONMENT_COLOR')

# Values that need to be set in local_settings.py
SECRET_KEY = get_setting('SECRET_KEY', 'secret')

# https SITE_URL assumes there is a proxy in front
SITE_URL = get_setting('SITE_URL', 'http://localhost:8000')
NOTIFY_URL = get_setting('NOTIFY_URL', SITE_URL)

# GUACAMOLE_URL_TEMPLATE uses three variables on templating:
#   env=settings.ENVIRONMENT_NAME
#   zone=self.boot_volume.zone.lower()
#   path=guac_utils.get_connection_path(self.guac_connection)
# e.g. GUACAMOLE_URL_TEMPLATE=http://{env}-guacamole-{zone}.example.com/{path}
GUACAMOLE_URL_TEMPLATE = get_setting('GUACAMOLE_URL_TEMPLATE')

OIDC_RP_CLIENT_SECRET = get_setting('OIDC_RP_CLIENT_SECRET')

FRESHDESK_DOMAIN = get_setting('FRESHDESK_DOMAIN')
FRESHDESK_KEY = get_setting('FRESHDESK_KEY')
FRESHDESK_GROUP_ID = get_setting('FRESHDESK_GROUP_ID')
FRESHDESK_EMAIL_CONFIG_ID = get_setting('FRESHDESK_EMAIL_CONFIG_ID')

EMAIL_BACKEND = 'researcher_workspace.utils.freshdesk.FreshdeskEmailBackend'

# Basic auth username/password for Prometheus metrics endpoint /metrics
METRICS_USERNAME = get_setting('METRICS_USERNAME', 'metrics')
METRICS_PASSWORD = get_setting('METRICS_PASSWORD')

if SITE_URL and SITE_URL.startswith('https'):
    USE_X_FORWARDED_HOST = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

try:
    from researcher_workspace.local_settings import *  # noqa
    logger.info('Imported local setting')
except ImportError:
    pass

COMPRESS_ENABLED = get_setting('COMPRESS_ENABLED', not DEBUG)
COMPRESS_OFFLINE = get_setting('COMPRESS_OFFLINE', not DEBUG)

# Expiry policy constants.  The values are (integer) days.
# - The 'expiry' is the initial expiry period.
# - The 'extension' is the (max) period added by the 'extend' button.
# - The 'lifetime' is the upper limit for extensions ... or -1 which
#   means no limit
# - The 'warnings' are the first and final warnings ... or -1 which
#   means no warnings.  The value is the time >before< the expiry deadline
#   that the warning notification will be sent.

BOOST_EXPIRY = int(get_setting('BOOST_EXPIRY', '7'))
BOOST_EXTENSION = int(get_setting('BOOST_EXTENSION', '7'))
BOOST_LIFETIME = int(get_setting('BOOT_LIFETIME', '14'))
BOOST_WARNING_1 = int(get_setting('BOOST_WARNING_1', '-1'))
BOOST_WARNING_2 = int(get_setting('BOOST_WARNING_2', '1'))

INSTANCE_EXPIRY = int(get_setting('INSTANCE_EXPIRY', '14'))
INSTANCE_EXTENSION = int(get_setting('INSTANCE_EXTENSION', '14'))
INSTANCE_LIFETIME = int(get_setting('INSTANCE_LIFETIME', '-1'))
INSTANCE_WARNING_1 = int(get_setting('INSTANCE_WARNING_1', '3'))
INSTANCE_WARNING_2 = int(get_setting('INSTANCE_WARNING_2', '1'))

# There is no 'extend' functionality for shelved volumes, so the
# the 'extension' and 'lifetime' settings would not be meaningful.
VOLUME_EXPIRY = int(get_setting('SHELVED_VOLUME_EXPIRY', '30'))
VOLUME_WARNING_1 = int(get_setting('SHELVED_VOLUME_WARNING_1', '7'))
VOLUME_WARNING_2 = int(get_setting('SHELVED_VOLUME_WARNING_2', '1'))

# OpenID Connect settings
OIDC_OP_AUTHORIZATION_ENDPOINT = f'{OIDC_SERVER_URL}/auth'
OIDC_OP_TOKEN_ENDPOINT = f'{OIDC_SERVER_URL}/token'
OIDC_OP_USER_ENDPOINT = f'{OIDC_SERVER_URL}/userinfo'
OIDC_OP_JWKS_ENDPOINT = f'{OIDC_SERVER_URL}/certs'

# Expand settings based on DEBUG override from local_settings.py
if DEBUG:
    MESSAGE_LEVEL = message_constants.DEBUG
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Whether to require authN with AAF (Australian Access Federation).
REQUIRE_AAF = strtobool(get_setting('REQUIRE_AAF', 'True'))
