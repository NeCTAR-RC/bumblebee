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

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.2/howto/deployment/checklist/

ADMINS = [('Andy', 'andy.botting@ardc.edu.au'),
          ('Stephen', 'stephen.crawley@ardc.edu.au')]

MANAGERS = ADMINS

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = []

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
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'researcher_workspace.auth.NectarAuthBackend',
]

# OpenID Connect Auth settings
OIDC_RP_SIGN_ALGO = 'RS256'
OIDC_USERNAME_ALGO = 'researcher_workspace.auth.generate_username'

AUTH_USER_MODEL = 'researcher_workspace.User'

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

OS_AUTH_URL = "https://keystone.rc.nectar.org.au:5000/v3/"
OS_AUTH_TYPE = 'v3applicationcredential'
OS_AVAILABILITY_ZONE = 'melbourne-qh2'
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

USER_LIMIT = 350  # 200 researchers + 25 support staff + 25 non-valid users we've got so far

# The page that users are redirected to after using invitation token
NEXT_PAGE = '/home'

# Empty warning message, should be filled in local_settings
GENERAL_WARNING_MESSAGE = ""

# Values that need to be set in local_settings.py
PROXY_URL = False
SECRET_KEY = ''
OS_APPLICATION_CREDENTIAL_ID = ''
OS_APPLICATION_CREDENTIAL_SECRET = ''

OS_KEYNAME = ''
ENVIRONMENT_NAME = ''
ENVIRONMENT_COLOR = ''
NOTIFY_URL = ''
SITE_URL = ''
GUACAMOLE_URL = ''
LINUX_IMAGE_NAME = ''
ALLOCATION_ID = ''

from researcher_workspace.local_settings import *

# Stuff can happen from this point that is useful for deployer, need to get a logger now
logger = logging.getLogger(__name__)


def _assert_not_empty(param, param_name):
    if len(param) == 0:
        raise Exception(f"{param_name} is empty")


# Checking that mandatory parameters from local_settings.py has been set
try:
    # Django settings
    DEBUG  # To check that DEBUG is defined
    _assert_not_empty(SECRET_KEY, 'SECRET_KEY')
    _assert_not_empty(ALLOWED_HOSTS, 'ALLOWED_HOSTS')

    # OpenStack Settings
    _assert_not_empty(OS_APPLICATION_CREDENTIAL_ID, 'OS_APPLICATION_CREDENTIAL_ID')
    _assert_not_empty(OS_APPLICATION_CREDENTIAL_SECRET, 'OS_APPLICATION_CREDENTIAL_SECRET')
    _assert_not_empty(OS_KEYNAME, 'OS_KEYNAME')

    # Researcher Desktop Settings
    _assert_not_empty(ENVIRONMENT_NAME, 'ENVIRONMENT_NAME')
    _assert_not_empty(ENVIRONMENT_COLOR, 'ENVIRONMENT_COLOR')
    _assert_not_empty(NOTIFY_URL, 'NOTIFY_URL')
    _assert_not_empty(SITE_URL, 'SITE_URL')
    _assert_not_empty(GUACAMOLE_URL, 'GUACAMOLE_URL')
    _assert_not_empty(LINUX_IMAGE_NAME, 'LINUX_IMAGE_NAME')

    # Auth Settings
    _assert_not_empty(OIDC_SERVER_URL, 'OIDC_SERVER_URL')

    # Reporting Settings
    _assert_not_empty(ALLOCATION_ID, "ALLOCATION_ID")

except Exception as e:
    logger.error('Settings failure: ' + str(e))
    exit()


# Expand settings based on DEBUG override from local_settings.py
if DEBUG:
    logger.info('DEBUG is True')
    MESSAGE_LEVEL = message_constants.DEBUG

    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    LOGGING['handlers']['log_file']['filename'] = 'dashboard_app.log'
    # override so we don't get duplicate console messages from the root logger
    LOGGING['loggers']['researcher_workspace']['propagate'] = False
    LOGGING['loggers']['vm_manager']['propagate'] = False

    # Email content is displayed on the console
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    logger.info('DEBUG is False')

RQ_QUEUES = {
    'default': {
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 0,
        'DEFAULT_TIMEOUT': 360,
    },
}

# OpenID Connect settings
OIDC_OP_AUTHORIZATION_ENDPOINT = f'{OIDC_SERVER_URL}/auth'
OIDC_OP_TOKEN_ENDPOINT = f'{OIDC_SERVER_URL}/token'
OIDC_OP_USER_ENDPOINT = f'{OIDC_SERVER_URL}/userinfo'
OIDC_OP_JWKS_ENDPOINT = f'{OIDC_SERVER_URL}/certs'

# Email Settings
EMAIL_HOST = 'smtp.unimelb.edu.au'
SERVER_EMAIL = DEFAULT_FROM_EMAIL = ENVIRONMENT_NAME

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
