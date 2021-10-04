import factory
from factory import fuzzy, random

import uuid
from datetime import datetime, timezone


class FuzzyUUID(fuzzy.BaseFuzzyAttribute):

    def fuzz(self):
        rand_int = random.randgen.getrandbits(128)
        return uuid.UUID(int=rand_int)


class InstanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'vm_manager.Instance'

    id = FuzzyUUID()
    created = datetime.now(timezone.utc)


class VolumeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'vm_manager.Volume'

    id = FuzzyUUID()
    flavor = FuzzyUUID()
    created = datetime.now(timezone.utc)


class VMStatusFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'vm_manager.VMStatus'
