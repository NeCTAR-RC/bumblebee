import factory
from factory import fuzzy, random
import uuid


class FuzzyUUID(fuzzy.BaseFuzzyAttribute):

    def fuzz(self):
        rand_int = random.randgen.getrandbits(128)
        return uuid.UUID(int=rand_int)


class InstanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'vm_manager.Instance'

    id = FuzzyUUID()


class VolumeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'vm_manager.Volume'

    id = FuzzyUUID()
    flavor = FuzzyUUID()


class VMStatusFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'vm_manager.VMStatus'

