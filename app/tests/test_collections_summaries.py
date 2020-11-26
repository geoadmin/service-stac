import logging
from datetime import datetime

from django.test import TestCase

from stac_api.models import Asset
from stac_api.models import Item
from stac_api.utils import utc_aware

import tests.database as db

logger = logging.getLogger(__name__)


class CollectionsSummariesTestCase(TestCase):

    y200 = utc_aware(datetime.strptime('0200-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
    y8000 = utc_aware(datetime.strptime('8000-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))

    def setUp(self):
        self.collection = db.create_collection('collection-1')

    def add_range_item(self, start, end, name):
        item = Item.objects.create(
            collection=self.collection,
            name=name,
            properties_start_datetime=start,
            properties_end_datetime=end,
            properties_title="My title",
        )
        db.create_item_links(item)
        item.full_clean()
        item.save()
        self.collection.save()
        return item

    def add_single_datetime_item(self, datetime_val, name):
        item = Item.objects.create(
            collection=self.collection,
            name=name,
            properties_datetime=datetime_val,
            properties_title="My Title",
        )
        db.create_item_links(item)
        item.full_clean()
        item.save()
        self.collection.save()
        return item

    def add_asset(self, item, name, eo_gsd, geoadmin_variant, proj_epsg):
        asset = Asset.objects.create(
            item=item,
            title='my-title',
            name=name,
            checksum_multihash="01205c3fd6978a7d0b051efaa4263a09",
            description="this an asset",
            eo_gsd=eo_gsd,
            geoadmin_lang="fr",
            geoadmin_variant=geoadmin_variant,
            proj_epsg=proj_epsg,
            media_type="image/tiff; application=geotiff; profile=cloud-optimize",
            href=
            "https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk50.noscale/smr200-200-1-2019-2056-kgrs-10.tiff"
        )
        asset.full_clean()
        asset.save()
        item.save()
        self.collection.save()
        return asset

    def test_update_collection_summaries_asset_insertion(self):
        # Tests if the collection's summaries are updated when an asset is
        # added to the collection's two items

        item1 = self.add_range_item(self.y200, self.y8000, "item1")
        item2 = self.add_range_item(self.y200, self.y8000, "item2")

        asset1 = self.add_asset(item1, "asset1", 1.2, "kgrs", 1234)
        self.assertEqual(
            self.collection.summaries["eo:gsd"], [1.2],
            "Collection's summaries[eo:gsd] has not been correctly updated "
            "after asset has been inserted."
        )
        self.assertEqual(
            self.collection.summaries["geoadmin:variant"], ["kgrs"],
            "Collection's summaries[geoadmin:variant] has not been correctly "
            " updated after asset has been inserted."
        )
        self.assertEqual(
            self.collection.summaries["proj:epsg"], [1234],
            "Collection's summaries[proj:epsg] has not been correctly updated "
            "after asset has been inserted."
        )

        asset2 = self.add_asset(item2, "asset2", 2.1, "komb", 4321)
        self.assertEqual(
            self.collection.summaries["eo:gsd"], [1.2, 2.1],
            "Collection's summaries[eo:gsd] has not been correctly updated "
            "after asset has been inserted."
        )
        self.assertEqual(
            self.collection.summaries["geoadmin:variant"], ["kgrs", "komb"],
            "Collection's summaries[geoadmin:variant] has not been correctly "
            "updated after asset has been inserted."
        )
        self.assertEqual(
            self.collection.summaries["proj:epsg"], [1234, 4321],
            "Collection's summaries[proj:epsg] has not been correctly updated "
            "after asset has been inserted."
        )

    def test_update_collection_summaries_asset_deletion(self):
        # Tests if the collection's summaries are updated when assets are
        # deleted from the collection

        item1 = self.add_range_item(self.y200, self.y8000, "item1")

        asset1 = self.add_asset(item1, "asset1", 1.2, "kgrs", 1234)
        asset2 = self.add_asset(item1, "asset2", 2.1, "komb", 4321)

        Asset.objects.get(pk=asset2.pk).delete()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.summaries["eo:gsd"], [asset1.eo_gsd],
            "Collection's summaries[eo:gsd] has not been correctly updated "
            "after asset has been deleted."
        )
        self.assertEqual(
            self.collection.summaries["geoadmin:variant"], [asset1.geoadmin_variant],
            "Collection's summaries[geoadmin:variant] has not been coorectly "
            "updated after assed has been deleted."
        )
        self.assertEqual(
            self.collection.summaries["proj:epsg"], [asset1.proj_epsg],
            "Collection's summaries[proj:epsg] has not been correctly updated "
            "after asset has been deleted."
        )

        Asset.objects.get(pk=asset1.pk).delete()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.summaries["eo:gsd"], [],
            "Collection's summaries[eo:gsd] has not been correctly updated "
            "after asset has been deleted."
        )
        self.assertEqual(
            self.collection.summaries["geoadmin:variant"], [],
            "Collection's summaries[geoadmin:variant] has not been coorectly "
            "updated after assed has been deleted."
        )
        self.assertEqual(
            self.collection.summaries["proj:epsg"], [],
            "Collection's summaries[proj:epsg] has not been correctly updated "
            "after asset has been deleted."
        )

    def test_update_collection_summaries_asset_update(self):
        # Tests if collection's summaries are updated correctly after an
        # asset was updated
        item1 = self.add_range_item(self.y200, self.y8000, "item1")
        asset1 = self.add_asset(item1, "asset1", 1.2, "kgrs", 1234)
        asset2 = self.add_asset(item1, "asset2", 2.1, "komb", 4321)

        asset1.eo_gsd = 12.34
        asset1.geoadmin_variant = "krel"
        asset1.proj_epsg = 9999
        asset1.full_clean()
        asset1.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.summaries["eo:gsd"], [2.1, 12.34],
            "Collection's summaries[eo:gsd] has not been correctly "
            "updated after asset has been inserted."
        )
        self.assertEqual(
            self.collection.summaries["geoadmin:variant"], ["komb", "krel"],
            "Collection's summaries[geoadmin:variant] has not been "
            "correctly updated after asset has been inserted."
        )
        self.assertEqual(
            self.collection.summaries["proj:epsg"], [4321, 9999],
            "Collection's summaries[proj:epsg] has not been correctly "
            "updated after asset has been inserted."
        )
