from django.core.management.base import BaseCommand, CommandError

from api.models import ServiceToken


class Command(BaseCommand):
    help = ('Create a REST API service token that is not tied to a '
            'user account. The key is shown once and stored hashed; '
            'if it is lost, deactivate the token and create a new one.')

    def add_arguments(self, parser):
        parser.add_argument(
            'name',
            help='A name identifying the consumer, e.g. reporting-cron')

    def handle(self, *args, **options):
        name = options['name']
        if ServiceToken.objects.filter(name=name).exists():
            raise CommandError(
                f"A service token named '{name}' already exists. "
                "Deactivate or delete it first to reissue.")
        token, key = ServiceToken.generate(name)
        self.stdout.write(f'Service token created: {token.name}')
        self.stdout.write(f'Key (shown once, store securely): {key}')
