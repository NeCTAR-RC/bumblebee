from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Promote a superuser'


    def add_arguments(self, parser):
        parser.add_argument('users', nargs='+', type=str)

    def handle(self, *args, **options):
        User = get_user_model()
        for username in options['users']:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError('User "%s" does not exist' % username)

            user.is_staff = True
            user.is_admin = True
            user.is_superuser = True
            user.save()

            self.stdout.write(self.style.SUCCESS(
                'Successfully promoted "%s"' % username))
