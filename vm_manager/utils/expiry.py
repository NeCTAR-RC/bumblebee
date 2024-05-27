from datetime import datetime, timedelta, timezone

from django.conf import settings


utc = timezone.utc


class ExpiryPolicy(object):

    def __init__(self, expiry_period, extend_period, max_lifetime=-1):
        '''Construct an expiry policy.  The arguments are the number
        of days to for the initial expiry, for extensions, and an (optional)
        lifetime limit in days for the resource.
        '''

        self.expiry_period = expiry_period
        self.extend_period = extend_period
        self.max_lifetime = max_lifetime

    def _get_expires(self, resource) -> datetime:
        return resource.get_expires()

    def _get_created(self, resource) -> datetime:
        return resource.created

    def permitted_extension(self, resource, now=None) -> timedelta:
        '''Compute how much extra time to add to the resource's expiry when
        the 'extend' button is pressed.

        The default amount to add is 'expiry_period', but that should not
        take the resource beyond the 'max_lifetime'.  If no expiry
        is currently set, extension is not permitted.  If 'max_lifetime'
        is -1, indefinite extension is permitted.
        '''

        if not now:
            now = datetime.now(utc)
        expires = self._get_expires(resource)
        created = self._get_created(resource)
        if not expires:
            # No expiration date set on this resource
            return timedelta(seconds=0)
        new_expires = now + timedelta(days=self.extend_period)
        if new_expires <= expires:
            # An extend should not reduce the current expiry time
            # (If you need to do that, do it by hand.)  This deals
            # with the case where an expiration date has been set
            # by hand.  We don't want the user to see an "extend"
            # button that actually >reduces< the expiration time.
            return timedelta(seconds=0)
        if self.max_lifetime >= 0:
            limit = created + timedelta(days=self.max_lifetime)
            new_expires = min(new_expires, limit)
        seconds = (new_expires - now).total_seconds()
        return timedelta(seconds=max(0, seconds))

    def initial_expiry(self, now=None) -> datetime:
        '''Compute the initial expiry datetime for the resource.
        '''
        if not now:
            now = datetime.now(utc)
        return now + timedelta(days=self.expiry_period)

    def new_expiry(self, resource, now=None) -> datetime:
        '''Compute the new expiry datetime for the resource after extending.
        '''
        if not now:
            now = datetime.now(utc)
        permitted_extension = self.permitted_extension(resource, now=now)
        if permitted_extension.total_seconds() > 0:
            return now + permitted_extension
        else:
            # Unchanged
            return self._get_expires(resource)


class VolumeExpiryPolicy(ExpiryPolicy):

    def __init__(self):
        super().__init__(expiry_period=settings.VOLUME_EXPIRY,
                         extend_period=0,
                         max_lifetime=-1)


class InstanceExpiryPolicy(ExpiryPolicy):

    def __init__(self):
        super().__init__(expiry_period=settings.INSTANCE_EXPIRY,
                         extend_period=settings.INSTANCE_EXTENSION,
                         max_lifetime=settings.INSTANCE_LIFETIME)


class BoostExpiryPolicy(ExpiryPolicy):

    def __init__(self):
        super().__init__(expiry_period=settings.BOOST_EXPIRY,
                         extend_period=settings.BOOST_EXTENSION,
                         max_lifetime=settings.BOOST_LIFETIME)

    def _get_created(self, resize) -> datetime:
        return resize.requested
