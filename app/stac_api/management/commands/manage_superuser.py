from typing import Any

import environ

from django.contrib.auth import get_user_model

from stac_api.utils import CommandHandler
from stac_api.utils import CustomBaseCommand

env = environ.Env()


class Handler(CommandHandler):
    """Create or update superuser from information from the environment

    This command is used to make sure that the superuser is created and
    configured. The data for it will be created centrally in terraform.
    This will help with the password rotation.
    """

    def run(self) -> None:
        User = get_user_model()  # pylint: disable=invalid-name
        username = env.str('DJANGO_SUPERUSER_USERNAME', default='').strip()
        email = env.str('DJANGO_SUPERUSER_EMAIL', default='').strip()
        password = env.str('DJANGO_SUPERUSER_PASSWORD', default='').strip()

        if not username or not email or not password:
            self.print_error('Environment variables not set or empty')
            return

        try:
            admin = User.objects.get(username=username)
            operation = 'Updated'
        except User.DoesNotExist:
            admin = User.objects.create(username=username)
            operation = 'Created'

        admin.set_password(password)
        admin.email = email
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()

        self.print_success('%s the superuser %s', operation, username)


class Command(CustomBaseCommand):
    help = "Superuser management (creating or updating)"

    def handle(self, *args: Any, **options: Any) -> None:
        Handler(self, options).run()
