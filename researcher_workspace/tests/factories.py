import random

import factory
from factory import fuzzy


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'researcher_workspace.User'

    username = fuzzy.FuzzyText(length=8)
    email = fuzzy.FuzzyText(length=8, suffix='@example.com')
