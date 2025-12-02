import time

from django.db import connection

from stac_api.utils import CommandHandler
from stac_api.utils import CustomBaseCommand


class Handler(CommandHandler):

    def run(self):
        self.print_success('running query to update counter tables...')

        start = time.monotonic()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                -- Fill gsd count based on asset values.
                TRUNCATE stac_api_gsdcount;
                INSERT INTO stac_api_gsdcount (collection_id, value, count)
                SELECT item.collection_id, asset.eo_gsd, COUNT(*) AS count
                FROM stac_api_asset asset
                    INNER JOIN stac_api_item item ON asset.item_id = item.id
                GROUP BY item.collection_id, asset.eo_gsd;

                -- Fill geoadmin_lang count based on asset values.
                TRUNCATE stac_api_geoadminlangcount;
                INSERT INTO stac_api_geoadminlangcount (collection_id, value, count)
                SELECT item.collection_id, asset.geoadmin_lang, COUNT(*) AS count
                FROM stac_api_asset asset
                    INNER JOIN stac_api_item item ON asset.item_id = item.id
                GROUP BY item.collection_id, asset.geoadmin_lang;

                -- Fill geoadmin_variant count based on asset values.
                TRUNCATE stac_api_geoadminvariantcount;
                INSERT INTO stac_api_geoadminvariantcount (collection_id, value, count)
                SELECT item.collection_id, asset.geoadmin_variant, COUNT(*) AS count
                FROM stac_api_asset asset
                    INNER JOIN stac_api_item item ON asset.item_id = item.id
                GROUP BY item.collection_id, asset.geoadmin_variant;

                -- Fill proj_epsg count based on asset and collection asset values.
                TRUNCATE stac_api_projepsgcount;
                INSERT INTO stac_api_projepsgcount (collection_id, value, count)
                SELECT collection_id, proj_epsg, COUNT(*) AS count
                FROM (
                    SELECT item.collection_id, asset.proj_epsg
                    FROM stac_api_asset asset
                        INNER JOIN stac_api_item item ON asset.item_id = item.id
                    UNION
                    SELECT collection_id, proj_epsg
                    FROM stac_api_collectionasset
                ) assets
                GROUP BY collection_id, proj_epsg;
                """
            )
        self.print_success(
            f"successfully updated counter tables in {(time.monotonic()-start):.3f}s"
        )


class Command(CustomBaseCommand):
    help = """Reset the summary counter tables.

    Truncates all the summary counter tables and repopulates with current data to make sure they are
    in sync with the values in the asset table. Unless the triggers are disabled or values in the
    counter tables are changed manually, this should not be required.
    """

    def handle(self, *args, **options):
        Handler(self, options).run()
