from datetime import timedelta

from django.conf import settings
from django.core.management.base import CommandParser
from django.utils import timezone

from stac_api.models import Asset
from stac_api.models import Item
from stac_api.utils import CommandHandler
from stac_api.utils import CustomBaseCommand


def boolean_input(question, default=None):
    result = input(f"{question}")
    if not result and default is not None:
        return default
    return len(result) > 0 and result[0].lower() == "y"


class Handler(CommandHandler):

    def delete(self, instance, object_type):
        if self.options['dry_run']:
            self.print_success(f'skipping deletion of {object_type} {instance}')
        else:
            instance.delete()

    def run(self):
        # print(self.options)
        self.print_success('running command to remove expired items')
        min_age_hours = self.options['min_age_hours']
        self.print_warning(f"deleting all items expired longer than {min_age_hours} hours")
        items = Item.objects.filter(
            properties_expires__lte=timezone.now() - timedelta(hours=min_age_hours)
        ).all()
        for i in items:
            assets = Asset.objects.filter(item_id=i.id).all()
            assets_length = len(assets)
            self.delete(assets, 'assets')
            self.delete(i, 'item')
            if not self.options['dry_run']:
                self.print_success(
                    f"deleted item {i.name} and {assets_length}" + " assets belonging to it.",
                    extra={"item": i.name}
                )

        if self.options['dry_run']:
            self.print_success(f'[dry run] would have removed {len(items)} expired items')
        else:
            self.print_success(f'successfully removed {len(items)} expired items')


class Command(CustomBaseCommand):
    help = """Remove items and their assets that have expired more than
    DELETE_EXPIRED_ITEMS_OLDER_THAN_HOURS hours ago.
    This command is thought to be scheduled as cron job.
    """

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate deleting items, without actually deleting them'
        )
        default_min_age = settings.DELETE_EXPIRED_ITEMS_OLDER_THAN_HOURS
        parser.add_argument(
            '--min-age-hours',
            type=int,
            default=default_min_age,
            help=f"Minimum hours the item must have been expired for (default {default_min_age})"
        )

    def handle(self, *args, **options):
        Handler(self, options).run()
