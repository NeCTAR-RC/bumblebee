import factory


class GuacamoleConnectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'guacamole.GuacamoleConnection'
