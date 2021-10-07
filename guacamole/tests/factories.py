import factory
from factory import fuzzy, random

import uuid


class GuacamoleConnectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'guacamole.GuacamoleConnection'
