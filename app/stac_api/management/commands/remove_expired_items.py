import functools
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


class SafetyAbort(Exception):

    def __str__(self):
        return (f"Attempting to delete too many items:"
                f" {self.args[1]} > {self.args[0]}.")


class Handler(CommandHandler):

    def delete(self, instance, object_type):
        if self.options['dry_run']:
            self.print_success(f'skipping deletion of {object_type} {instance}')
        else:
            instance.delete()

    def _raise_if_too_many_deletions(self, max_deletions, max_deletions_pct, items_count):
        if items_count > max_deletions:
            exception = SafetyAbort(max_deletions, items_count)
            self.print_error("%s", str(exception))
            raise exception

        items_deleted_pct = 100 * items_count / Item.objects.count()
        if items_deleted_pct > max_deletions_pct:
            exception = SafetyAbort(f"{int(max_deletions_pct)}%", f"{items_deleted_pct:.2f}%")
            self.print_error("%s", str(exception))
            raise exception

    def run(self):
        self.print_success('running command to remove expired items')
        min_age_hours = self.options['min_age_hours']
        max_deletions = self.options['max_deletions']
        max_deletions_pct = self.options['max_deletions_percentage']
        self.print_warning(
            f"deleting no more than {max_deletions} or "
            f"{max_deletions_pct}%% items expired for longer"
            f" than {min_age_hours} hours"
        )

        expiration = timezone.now() - timedelta(hours=min_age_hours)

        items = Item.objects.filter(properties_expires__lte=expiration)
        items_count = items.count()

        self._raise_if_too_many_deletions(max_deletions, max_deletions_pct, items_count)

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

    def _validate_int(self, candidate, min_value=None, max_value=None):
        value = int(candidate)
        if min_value is not None and value < min_value:
            raise ValueError(f"{value} is less than {min_value}")
        if max_value is not None and value > max_value:
            raise ValueError(f"{value} is greater than {max_value}")
        return value

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.register('type', 'positive_int', functools.partial(self._validate_int, min_value=0))
        parser.register(
            'type',
            'percentage_int',
            functools.partial(self._validate_int, min_value=0, max_value=100)
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate deleting items, without actually deleting them'
        )
        default_min_age = settings.DELETE_EXPIRED_ITEMS_OLDER_THAN_HOURS
        parser.add_argument(
            '--min-age-hours',
            type='positive_int',
            default=default_min_age,
            help=f"Minimum hours the item must have been expired for (default {default_min_age})"
        )
        default_max_deletions = settings.DELETE_EXPIRED_ITEMS_MAX
        parser.add_argument(
            '--max-deletions',
            type='positive_int',
            default=default_max_deletions,
            help=(
                f"Maximum number of items to delete. If that number of items"
                f" have expired, this programm will fail. Default value:"
                f" {default_max_deletions}."
            )
        )
        default_max_deletions_percentage = settings.DELETE_EXPIRED_ITEMS_MAX_PERCENTAGE
        parser.add_argument(
            '--max-deletions-percentage',
            type='percentage_int',
            default=default_max_deletions_percentage,
            help=(
                f"Maximum percentage of items to delete. If that percentage of"
                f" items are expired, this program will fail."
                f" Default value: {default_max_deletions_percentage}."
            )
        )

    def handle(self, *args, **options):
        Handler(self, options).run()
