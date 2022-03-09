import factory
from factory import fuzzy


class DesktopTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'researcher_desktop.DesktopType'

    name = fuzzy.FuzzyText(length=8)


class AvailabilityZoneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'researcher_desktop.AvailabilityZone'


class DomainFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'researcher_desktop.Domain'
