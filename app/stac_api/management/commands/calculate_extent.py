import time

from django.core.management.base import CommandParser
from django.db import connection

from stac_api.models import Collection
from stac_api.utils import CommandHandler
from stac_api.utils import CustomBaseCommand


def boolean_input(question, default=None):
    result = input(f"{question}")
    if not result and default is not None:
        return default
    return len(result) > 0 and result[0].lower() == "y"


class Handler(CommandHandler):

    def run(self):
        self.print_success('running command to update collection extents')
        # print(self.options)
        qry = Collection.objects.filter(extent_out_of_sync=True)
        if self.options['all']:
            qry = Collection.objects
        collections = qry.values_list('id', flat=True)

        # Prompt user to confirm update of all collections if force was not provided.
        if self.options['all'] and not self.options['force']:
            cont = boolean_input(
                f"You are about to update {len(collections)} collections!\n" +
                "Are you sure you want to continue? (y/n): ",
                False
            )
            if not cont:
                self.print_warning("Aborted")
                self.print_success("No collections updated")
                return

        start = time.monotonic()
        with connection.cursor() as cursor:
            for collection_id in collections:
                cursor.execute(
                    """
                    -- Compute collection extent
                    WITH collection_extent AS (
                        SELECT
                            item.collection_id,
                            ST_SetSRID(ST_EXTENT(item.geometry),4326) as extent_geometry,
                            MIN(LEAST(item.properties_datetime, item.properties_start_datetime))
                                as extent_start_datetime,
                            MAX(GREATEST(item.properties_datetime, item.properties_end_datetime))
                                as extent_end_datetime
                        FROM stac_api_item AS item
                        WHERE item.collection_id = %s
                        GROUP BY item.collection_id
                    UNION
                        -- This covers the case that the last item of a collection is deleted.
                        SELECT %s AS collection_id, NULL, NULL, NULL
                    ORDER BY extent_geometry, extent_start_datetime, extent_end_datetime
                    LIMIT 1
                    )
                    -- Update related collection extent
                    UPDATE stac_api_collection SET
                        extent_out_of_sync = FALSE,
                        extent_geometry = collection_extent.extent_geometry,
                        extent_start_datetime = collection_extent.extent_start_datetime,
                        extent_end_datetime = collection_extent.extent_end_datetime
                    FROM collection_extent
                    WHERE id = collection_extent.collection_id;
                    """, [collection_id, collection_id]
                )
                self.print_success(
                    f"collection.id={collection_id} extent updated.",
                    extra={"collection": collection_id}
                )
        self.print_success(
            f"successfully updated extent of {len(collections)} collections",
            extra={"duration": time.monotonic() - start}
        )


class Command(CustomBaseCommand):
    help = """Calculate the collection spacial and temporal extent for all collections that have
    'extent_out_of_sync' set to true. After update, 'extent_out_of_sync' will be set to False.
    This command is thought to be scheduled as cron job.
    """

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            '-a', '--all', action='store_true', help='Update extent for all collections'
        )
        parser.add_argument(
            '-f', '--force', action='store_true', help='Run all without confirmation'
        )

    def handle(self, *args, **options):
        Handler(self, options).run()
