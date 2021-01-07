import logging
from datetime import datetime

from django.test import TestCase

from stac_api.utils import utc_aware

from tests.data_factory import Factory
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)


class CollectionsSummariesTestCase(TestCase):

    y200 = utc_aware(datetime.strptime('0200-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
    y8000 = utc_aware(datetime.strptime('8000-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))

    @classmethod
    @mock_s3_asset_file
    def setUpTestData(cls):
        cls.data_factory = Factory()

    @mock_s3_asset_file
    def setUp(self):
        self.collection = self.data_factory.create_collection_sample(
            name='collection-test-summaries-auto-update', db_create=True
        ).model

    # def tearDown(self):
    #     self.collection.delete()

    def add_range_item(self, start, end, name):
        item = self.data_factory.create_item_sample(
            collection=self.collection,
            name=name,
            sample='item-2',
            properties_start_datetime=start,
            properties_end_datetime=end,
        ).model
        return item

    def add_single_datetime_item(self, datetime_val, name):
        item = self.data_factory.create_item_sample(
            collection=self.collection,
            name=name,
            properties_datetime=datetime_val,
        ).model
        return item

    def add_asset(self, item, name, eo_gsd, geoadmin_variant, proj_epsg):
        asset = self.data_factory.create_asset_sample(
            item=item,
            name=name,
            eo_gsd=eo_gsd,
            geoadmin_variant=geoadmin_variant,
            proj_epsg=proj_epsg
        ).model
        return asset

    def test_update_collection_summaries_asset_insertion(self):
        # Tests if the collection's summaries are updated when an asset is
        # added to the collection's two items

        item1 = self.add_range_item(self.y200, self.y8000, "item1")
        item2 = self.add_range_item(self.y200, self.y8000, "item2")

        self.add_asset(item1, "asset1", 1.2, "kgrs", 1234)

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

        self.add_asset(item2, "asset2", 2.1, "komb", 4321)
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

        asset2.delete()

        self.assertEqual(
            self.collection.summaries["eo:gsd"], [asset1.eo_gsd],
            "Collection's summaries[eo:gsd] has not been correctly updated "
            "after asset has been deleted."
        )
        self.assertEqual(
            self.collection.summaries["geoadmin:variant"], [asset1.geoadmin_variant],
            "Collection's summaries[geoadmin:variant] has not been correctly "
            "updated after asset has been deleted."
        )
        self.assertEqual(
            self.collection.summaries["proj:epsg"], [asset1.proj_epsg],
            "Collection's summaries[proj:epsg] has not been correctly updated "
            "after asset has been deleted."
        )

        asset1.delete()

        self.assertEqual(
            self.collection.summaries["eo:gsd"], [],
            "Collection's summaries[eo:gsd] has not been correctly updated "
            "after asset has been deleted."
        )
        self.assertEqual(
            self.collection.summaries["geoadmin:variant"], [],
            "Collection's summaries[geoadmin:variant] has not been correctly "
            "updated after asset has been deleted."
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
