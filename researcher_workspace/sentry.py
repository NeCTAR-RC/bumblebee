import logging
import os

import pbr.version
import sentry_sdk


LOG = logging.getLogger(__name__)


def _release():
    """Return "bumblebee@<version>", or None if pbr can't tell.

    The production container copies the source tree without installing
    the package or its git metadata, so pbr may not be able to derive
    a version there. Returning None lets sentry-sdk fall back to the
    SENTRY_RELEASE environment variable, if set.
    """
    try:
        version = pbr.version.VersionInfo('bumblebee').release_string()
    except Exception:
        return None
    return f'bumblebee@{version}'


def setup(dsn=None, environment=None):
    """Enable error reporting to GlitchTip/Sentry.

    A no-op unless a DSN is set (SENTRY_DSN in the environment,
    or in local_settings.py). Once enabled, the sentry-sdk default
    integrations report unhandled exceptions and ERROR level log
    messages.
    """
    dsn = dsn or os.environ.get('SENTRY_DSN')
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=_release(),
        # GlitchTip does not support sessions
        auto_session_tracking=False,
    )
    LOG.debug('Sentry error reporting enabled')
    return True
