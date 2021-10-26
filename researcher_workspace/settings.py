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
    if not value:
        secret_file_name = setting.lower() + '_store'
        secret_file_path = os.path.join('/vault/secrets', secret_file_name)
        if os.path.isfile(secret_file_path):
            value = secret_key.read_from_file(secret_file_path)
    if required and not value:
        #raise Exception(f'Setting value for {setting} not found!')
        logger.info('Setting value for %s not found!' % setting)
    return value


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
    'crispy_forms',
    'crispy_bootstrap5',
    'compressor',
    'guacamole',
    'researcher_workspace',
    'mathfilters',
    'django_rq',
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
        'ENGINE': get_setting('DB_ENGINE', 'django.db.backends.mysql'),
        'NAME': get_setting('DB_NAME', 'bumblebee'),
        'USER': get_setting('DB_USER'),
        'PASSWORD': get_setting('DB_PASSWORD'),
        'HOST': get_setting('DB_HOST'),
        'PORT': get_setting('DB_PORT', '3306'),
    }
}

# Redis queue
RQ_QUEUES = {
    'default': {
        'HOST': get_setting('REDIS_HOST', 'localhost'),
        'PORT': get_setting('REDIS_PORT', '6379'),
        'DB': 0,
        'DEFAULT_TIMEOUT': 360,
    },
}

# OpenStack config
OS_APPLICATION_CREDENTIAL_ID = get_setting('OS_APPLICATION_CREDENTIAL_ID')
OS_APPLICATION_CREDENTIAL_SECRET = get_setting('OS_APPLICATION_CREDENTIAL_SECRET')

OS_AUTH_URL = get_setting('OS_AUTH_URL', 'https://keystone.rc.nectar.org.au:5000/v3/')
OS_NETWORK = get_setting('OS_NETWORK', 'bumblebee')
OS_SECGROUPS = get_setting('OS_SECGROUPS', 'bumblebee').split(',')
OS_KEYNAME = get_setting('OS_KEYNAME', required=True)

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'researcher_workspace.auth.NectarAuthBackend',
]

AUTH_USER_MODEL = 'researcher_workspace.User'

# OpenID Connect Auth settings
OIDC_SERVER_URL = get_setting('OIDC_SERVER_URL', 'https://sso.rc.nectar.org.au/auth/realms/nectar/protocol/openid-connect')
OIDC_RP_CLIENT_ID = get_setting('OIDC_RP_CLIENT_ID', 'bumblebee')
OIDC_RP_SIGN_ALGO = 'RS256'
OIDC_USERNAME_ALGO = 'researcher_workspace.auth.generate_username'

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

COMPRESS_ENABLED = get_setting('COMPRESS_ENABLED', not DEBUG)
COMPRESS_OFFLINE = get_setting('COMPRESS_OFFLINE', not DEBUG)

COMPRESS_PRECOMPILERS = (
    ('text/x-scss', 'django_libsass.SassCompiler'),
)

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

LOGIN_REDIRECT_URL = reverse_lazy('home')
LOGOUT_REDIRECT_URL = reverse_lazy('index')

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# See:
# http://www.webforefront.com/django/setupdjangologging.html
# https://www.caktusgroup.com/blog/2015/01/27/Django-Logging-Configuration-logging_config-default-settings-logger/
# https://docs.djangoproject.com/en/2.2/topics/logging/

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[%(asctime)s] %(levelname)s %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
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

MESSAGE_TAGS = {
    messages.DEBUG: 'alert-info',
    messages.INFO: 'alert-info',
    messages.SUCCESS: 'alert-success',
    messages.WARNING: 'alert-warning',
    messages.ERROR: 'alert-danger',
}

# https://docs.djangoproject.com/en/2.2/ref/settings/#internal-ips
# must be set to localhost if we want to use 'debug' in templates...
INTERNAL_IPS = "127.0.0.1"

USER_LIMIT = 350

# The page that users are redirected to after using invitation token
NEXT_PAGE = '/home'

# Current version number for the terms and conditions
TERMS_VERSION = int(get_setting('TERMS_VERSION', 1))

# Users are limited to this number of workspaces.  Use zero for unlimited
LIMIT_WORKSPACES_PER_USER = int(get_setting('LIMIT_WORKSPACES_PER_USER', 1))

# If True, requests for new workspaces will be auto-approved
AUTO_APPROVE_WORKSPACES = bool(strtobool(get_setting('DEBUG', 'True')))

# A list of Features that are permitted by default when a Workspace
# is approved.  (A list of the Feature 'app_name' values.)
PROJECT_DEFAULT_FEATURES = ['researcher_desktop']

DESKTOP_TYPES = get_setting('DESKTOP_TYPES')
ZONES = get_setting('ZONES')

GENERAL_WARNING_MESSAGE = get_setting('GENERAL_WARNING_MESSAGE')
ENVIRONMENT_NAME = get_setting('ENVIRONMENT_NAME')
ENVIRONMENT_COLOR = get_setting('ENVIRONMENT_COLOR')

# Values that need to be set in local_settings.py
SECRET_KEY = get_setting('SECRET_KEY', 'secret')

SITE_URL = get_setting('SITE_URL', 'http://localhost:8000')
NOTIFY_URL = get_setting('NOTIFY_URL', SITE_URL)
GUACAMOLE_URL = get_setting('GUACAMOLE_URL', SITE_URL + '/guacamole')

OIDC_RP_CLIENT_SECRET = get_setting('OIDC_RP_CLIENT_SECRET')

if SITE_URL and SITE_URL.startswith('https'):
    USE_X_FORWARDED_HOST = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

try:
    from researcher_workspace.local_settings import *  # noqa
    logger.info('Imported local setting')
except ImportError:
    pass

# OpenID Connect settings
OIDC_OP_AUTHORIZATION_ENDPOINT = f'{OIDC_SERVER_URL}/auth'
OIDC_OP_TOKEN_ENDPOINT = f'{OIDC_SERVER_URL}/token'
OIDC_OP_USER_ENDPOINT = f'{OIDC_SERVER_URL}/userinfo'
OIDC_OP_JWKS_ENDPOINT = f'{OIDC_SERVER_URL}/certs'


# Expand settings based on DEBUG override from local_settings.py
if DEBUG:
    MESSAGE_LEVEL = message_constants.DEBUG
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
