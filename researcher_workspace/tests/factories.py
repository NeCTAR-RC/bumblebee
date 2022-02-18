import random

import factory
from factory import fuzzy

from faker import Faker

fake = Faker()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'researcher_workspace.User'

    email = factory.LazyAttribute(lambda _: fake.email())
    username = factory.SelfAttribute('email')
    first_name = factory.LazyAttribute(lambda _: fake.first_name())
    last_name = factory.LazyAttribute(lambda _: fake.last_name())
    sub = factory.LazyAttribute(lambda _: fake.unique.uuid4())


class ProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'researcher_workspace.Profile'


class FeatureFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'researcher_workspace.Feature'

    name = fuzzy.FuzzyText(length=16)
    description = fuzzy.FuzzyText(length=16)
    app_name = fuzzy.FuzzyText(length=8)


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'researcher_workspace.Project'

    title = fuzzy.FuzzyText(length=16)
    description = fuzzy.FuzzyText(length=64)
