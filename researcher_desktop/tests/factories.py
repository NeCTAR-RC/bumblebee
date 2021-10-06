import random

import factory
from factory import fuzzy


class DesktopTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'researcher_desktop.DesktopType'

    name = fuzzy.FuzzyText(length=8)
