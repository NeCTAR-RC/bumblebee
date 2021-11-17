import random

import factory
from factory import fuzzy


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'researcher_workspace.User'

    username = fuzzy.FuzzyText(length=8)
    email = fuzzy.FuzzyText(length=8, suffix='@example.com')


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
