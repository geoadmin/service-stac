from datetime import timedelta

from django.conf import settings
from django.core.management.base import CommandParser
from django.utils import timezone

from stac_api.models.general import AssetUpload
from stac_api.models.general import BaseAssetUpload
from stac_api.models.general import Item
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
        items = Item.objects.filter(
            properties_expires__lte=timezone.now() - timedelta(hours=min_age_hours)
        ).all()
        for item in items:
            assets = item.assets.all()
            uploads_in_progress = AssetUpload.objects.filter(
                asset__in=assets, status=BaseAssetUpload.Status.IN_PROGRESS
            )
            if uploads_in_progress.count() > 0:
                self.print_warning(
                    "WARNING: There are still pending asset uploads for expired items. "
                    "These are likely stale, so we'll abort them"
                )
                uploads_in_progress.update(status=BaseAssetUpload.Status.ABORTED)
            assets_length = len(assets)
            self.delete(assets, 'assets')
            self.delete(item, 'item')
            if not self.options['dry_run']:
                self.print_success(
                    f"deleted item {item.name} and {assets_length}" + " assets belonging to it.",
                    extra={"item": item.name}
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
