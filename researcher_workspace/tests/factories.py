import factory
from factory import fuzzy

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'researcher_workspace.User'

