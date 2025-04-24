from datetime import timedelta

from django.conf import settings
from django.core.management.base import CommandParser
from django.utils import timezone

from stac_api.models.general import BaseAssetUpload
from stac_api.models.item import Asset
from stac_api.models.item import AssetUpload
from stac_api.models.item import Item
from stac_api.utils import CommandHandler
from stac_api.utils import CustomBaseCommand


class Handler(CommandHandler):

    def delete(self, instance, object_type):
        if self.options['dry_run']:
            self.print_success(f'skipping deletion of {object_type} {instance}')
        else:
            instance.delete()

    def run(self):
        self.print_success('running command to remove expired items')
        min_age_hours = self.options['min_age_hours']
        self.print_warning(f"deleting all items expired longer than {min_age_hours} hours")
        expiration = timezone.now() - timedelta(hours=min_age_hours)

        items = Item.objects.filter(properties_expires__lte=expiration)
        items_count = items.count()
        assets = Asset.objects.filter(item__properties_expires__lte=expiration)
        asset_uploads = AssetUpload.objects.filter(
            asset__item__properties_expires__lte=expiration,
            status=BaseAssetUpload.Status.IN_PROGRESS
        )

        if asset_uploads.update(status=BaseAssetUpload.Status.ABORTED):
            self.print_warning(
                "WARNING: There were still pending asset uploads for expired items. "
                "These were likely stale, so we aborted them"
            )
        self.delete(assets, 'assets')
        self.delete(items, 'items')

        if self.options['dry_run']:
            self.print_success(f'[dry run] would have removed {items_count} expired items')
        else:
            self.print_success(f'successfully removed {items_count} expired items')


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
