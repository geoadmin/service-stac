import logging
from datetime import datetime

from django.core.management import call_command

from stac_api.models.collection import GeoadminLangCount
from stac_api.models.collection import GeoadminVariantCount
from stac_api.models.collection import GSDCount
from stac_api.models.collection import ProjEPSGCount
from stac_api.utils import utc_aware

from tests.tests_10.base_test import StacBaseTransactionTestCase
from tests.tests_10.data_factory import Factory
from tests.utils import MockS3PerTestMixin

logger = logging.getLogger(__name__)


# Here we need to use TransactionTestCase due to the pgtrigger, in a normal
# test case we cannot test effect of pgtrigger.
class CollectionsSummariesTestCase(MockS3PerTestMixin, StacBaseTransactionTestCase):

    y200 = utc_aware(datetime.strptime('0200-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
    y8000 = utc_aware(datetime.strptime('8000-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))

    def setUp(self):
        super().setUp()
        self.data_factory = Factory()
        self.collection = self.data_factory.create_collection_sample(
            name='collection-test-summaries-auto-update', db_create=True
        ).model

    def add_range_item(self, start, end, name):
        item = self.data_factory.create_item_sample(
            collection=self.collection,
            name=name,
            sample='item-2',
            properties_start_datetime=start,
            properties_end_datetime=end,
            db_create=True
        ).model
        return item

    def add_single_datetime_item(self, datetime_val, name):
        item = self.data_factory.create_item_sample(
            collection=self.collection,
            name=name,
            properties_datetime=datetime_val,
            db_create=True,
        ).model
        return item

    def add_asset(self, item, eo_gsd, geoadmin_variant, proj_epsg, geoadmin_lang=None):
        asset = self.data_factory.create_asset_sample(
            item=item,
            eo_gsd=eo_gsd,
            geoadmin_variant=geoadmin_variant,
            geoadmin_lang=geoadmin_lang,
            proj_epsg=proj_epsg,
            db_create=True
        ).model
        self.collection.refresh_from_db()
        return asset

    def add_collection_asset(self, proj_epsg):
        asset = self.data_factory.create_collection_asset_sample(
            collection=self.collection, proj_epsg=proj_epsg, db_create=True
        ).model
        self.collection.refresh_from_db()
        return asset

    def test_update_collection_summaries_asset_insertion(self):
        # Tests if the collection's summaries are updated when an asset is
        # added to the collection's two items

        item1 = self.add_range_item(self.y200, self.y8000, "item1")
        item2 = self.add_range_item(self.y200, self.y8000, "item2")

        self.add_asset(item1, 1.2, "kgrs", 1234, 'de')

        self.assertListEqual(
            self.collection.summaries_eo_gsd, [1.2],
            "Collection's summaries[gsd] has not been correctly updated "
            "after asset has been inserted."
        )
        self.assertListEqual(
            self.collection.summaries_geoadmin_variant, ["kgrs"],
            "Collection's summaries[geoadmin:variant] has not been correctly "
            " updated after asset has been inserted."
        )
        self.assertListEqual(
            self.collection.summaries_geoadmin_lang, ["de"],
            "Collection's summaries[geoadmin:lang] has not been correctly "
            " updated after asset has been inserted."
        )
        self.assertListEqual(
            self.collection.summaries_proj_epsg, [1234],
            "Collection's summaries[proj:epsg] has not been correctly updated "
            "after asset has been inserted."
        )

        self.add_asset(item2, 2.1, "komb", 4321, 'fr')

        self.assertListEqual(
            self.collection.summaries_eo_gsd, [1.2, 2.1],
            "Collection's summaries[gsd] has not been correctly updated "
            "after asset has been inserted."
        )
        self.assertListEqual(
            self.collection.summaries_geoadmin_variant, ["kgrs", "komb"],
            "Collection's summaries[geoadmin:variant] has not been correctly "
            "updated after asset has been inserted."
        )
        self.assertListEqual(
            self.collection.summaries_geoadmin_lang, ["de", "fr"],
            "Collection's summaries[geoadmin:lang] has not been correctly "
            "updated after asset has been inserted."
        )
        self.assertListEqual(
            self.collection.summaries_proj_epsg, [1234, 4321],
            "Collection's summaries[proj:epsg] has not been correctly updated "
            "after asset has been inserted."
        )

        self.add_collection_asset(5678)

        self.assertListEqual(
            self.collection.summaries_eo_gsd, [1.2, 2.1],
            "Collection's summaries[gsd] has not been correctly updated "
            "after asset has been inserted."
        )
        self.assertListEqual(
            self.collection.summaries_geoadmin_variant, ["kgrs", "komb"],
            "Collection's summaries[geoadmin:variant] has not been correctly "
            "updated after asset has been inserted."
        )
        self.assertListEqual(
            self.collection.summaries_geoadmin_lang, ["de", "fr"],
            "Collection's summaries[geoadmin:lang] has not been correctly "
            "updated after asset has been inserted."
        )
        self.assertCountEqual(
            self.collection.summaries_proj_epsg, [1234, 4321, 5678],
            "Collection's summaries[proj:epsg] has not been correctly updated "
            "after asset has been inserted."
        )

    def test_update_collection_summaries_asset_deletion(self):
        # Tests if the collection's summaries are updated when assets are
        # deleted from the collection

        item1 = self.add_range_item(self.y200, self.y8000, "item1")

        asset1 = self.add_asset(item1, 1.2, "kgrs", 1234, 'de')
        asset2 = self.add_asset(item1, 2.1, "komb", 4321, 'fr')
        col_asset1 = self.add_collection_asset(5678)

        asset2.delete()
        self.collection.refresh_from_db()

        self.assertCountEqual(
            self.collection.summaries_eo_gsd, [asset1.eo_gsd],
            "Collection's summaries[gsd] has not been correctly updated "
            "after asset has been deleted."
        )
        self.assertCountEqual(
            self.collection.summaries_geoadmin_variant, [asset1.geoadmin_variant],
            "Collection's summaries[geoadmin:variant] has not been correctly "
            "updated after asset has been deleted."
        )
        self.assertCountEqual(
            self.collection.summaries_geoadmin_lang, [asset1.geoadmin_lang],
            "Collection's summaries[geoadmin:lang] has not been correctly "
            "updated after asset has been deleted."
        )
        self.assertCountEqual(
            self.collection.summaries_proj_epsg, [asset1.proj_epsg, col_asset1.proj_epsg],
            "Collection's summaries[proj:epsg] has not been correctly updated "
            "after asset has been deleted."
        )

        col_asset1.delete()
        self.collection.refresh_from_db()

        self.assertListEqual(
            self.collection.summaries_eo_gsd, [asset1.eo_gsd],
            "Collection's summaries[gsd] has not been correctly updated "
            "after asset has been deleted."
        )
        self.assertListEqual(
            self.collection.summaries_geoadmin_variant, [asset1.geoadmin_variant],
            "Collection's summaries[geoadmin:variant] has not been correctly "
            "updated after asset has been deleted."
        )
        self.assertListEqual(
            self.collection.summaries_geoadmin_lang, [asset1.geoadmin_lang],
            "Collection's summaries[geoadmin:lang] has not been correctly "
            "updated after asset has been deleted."
        )
        self.assertListEqual(
            self.collection.summaries_proj_epsg, [asset1.proj_epsg],
            "Collection's summaries[proj:epsg] has not been correctly updated "
            "after asset has been deleted."
        )

        asset1.delete()
        self.collection.refresh_from_db()

        self.assertListEqual(
            self.collection.summaries_eo_gsd, [],
            "Collection's summaries[gsd] has not been correctly updated "
            "after asset has been deleted."
        )
        self.assertListEqual(
            self.collection.summaries_geoadmin_variant, [],
            "Collection's summaries[geoadmin:variant] has not been correctly "
            "updated after asset has been deleted."
        )
        self.assertListEqual(
            self.collection.summaries_geoadmin_lang, [],
            "Collection's summaries[geoadmin:lang] has not been correctly "
            "updated after asset has been deleted."
        )
        self.assertListEqual(
            self.collection.summaries_proj_epsg, [],
            "Collection's summaries[proj:epsg] has not been correctly updated "
            "after asset has been deleted."
        )

    def test_update_collection_summaries_empty_asset_delete(self):
        # This test has been introduced due to a bug when removing an asset without gsd,
        # proj:epsg and geoadmin:variant from a collections with summaries
        self.assertListEqual(self.collection.summaries_proj_epsg, [])
        self.assertListEqual(self.collection.summaries_geoadmin_variant, [])
        self.assertListEqual(self.collection.summaries_geoadmin_lang, [])
        self.assertListEqual(self.collection.summaries_eo_gsd, [])
        item = self.data_factory.create_item_sample(
            collection=self.collection, db_create=True
        ).model
        asset = self.data_factory.create_asset_sample(
            item=item,
            required_only=True,
            geoadmin_variant=None,
            geoadmin_lang=None,
            eo_gsd=None,
            proj_epsg=None,
            db_create=True
        ).model
        self.assertListEqual(self.collection.summaries_proj_epsg, [])
        self.assertListEqual(self.collection.summaries_geoadmin_variant, [])
        self.assertListEqual(self.collection.summaries_geoadmin_lang, [])
        self.assertListEqual(self.collection.summaries_eo_gsd, [])
        col_asset = self.data_factory.create_collection_asset_sample(
            collection=self.collection, required_only=True, proj_epsg=None, db_create=True
        ).model
        self.assertListEqual(self.collection.summaries_proj_epsg, [])
        self.assertListEqual(self.collection.summaries_geoadmin_variant, [])
        self.assertListEqual(self.collection.summaries_geoadmin_lang, [])
        self.assertListEqual(self.collection.summaries_eo_gsd, [])
        asset2 = self.data_factory.create_asset_sample(
            item=item,
            required_only=True,
            geoadmin_variant='krel',
            geoadmin_lang='en',
            eo_gsd=2,
            proj_epsg=2056,
            db_create=True
        ).model
        self.collection.refresh_from_db()
        self.assertIsNone(asset.geoadmin_variant)
        self.assertListEqual(self.collection.summaries_proj_epsg, [2056])
        self.assertListEqual(self.collection.summaries_geoadmin_variant, ['krel'])
        self.assertListEqual(self.collection.summaries_geoadmin_lang, ['en'])
        self.assertListEqual(self.collection.summaries_eo_gsd, [2])

        asset.delete()
        self.collection.refresh_from_db()
        self.assertListEqual(self.collection.summaries_proj_epsg, [2056])
        self.assertListEqual(self.collection.summaries_geoadmin_variant, ['krel'])
        self.assertListEqual(self.collection.summaries_geoadmin_lang, ['en'])
        self.assertListEqual(self.collection.summaries_eo_gsd, [2])
        col_asset.delete()
        self.collection.refresh_from_db()
        self.assertListEqual(self.collection.summaries_proj_epsg, [2056])
        self.assertListEqual(self.collection.summaries_geoadmin_variant, ['krel'])
        self.assertListEqual(self.collection.summaries_geoadmin_lang, ['en'])
        self.assertListEqual(self.collection.summaries_eo_gsd, [2])
        asset2.delete()
        self.collection.refresh_from_db()
        self.assertListEqual(self.collection.summaries_proj_epsg, [])
        self.assertListEqual(self.collection.summaries_geoadmin_variant, [])
        self.assertListEqual(self.collection.summaries_geoadmin_lang, [])
        self.assertListEqual(self.collection.summaries_eo_gsd, [])

    def test_update_collection_summaries_asset_update(self):
        # Tests if collection's summaries are updated correctly after an
        # asset was updated
        item1 = self.add_range_item(self.y200, self.y8000, "item1")
        asset1 = self.add_asset(item1, 1.2, "kgrs", 1234, 'de')
        asset2 = self.add_asset(item1, 2.1, "komb", 4321, 'fr')

        asset1.eo_gsd = 12.34
        asset1.geoadmin_variant = "krel"
        asset1.geoadmin_lang = "en"
        asset1.proj_epsg = 9999
        asset1.full_clean()
        asset1.save()
        self.collection.refresh_from_db()

        self.assertListEqual(
            self.collection.summaries_eo_gsd, [2.1, 12.34],
            "Collection's summaries[gsd] has not been correctly "
            "updated after asset has been inserted."
        )
        self.assertListEqual(
            self.collection.summaries_geoadmin_variant, ["komb", "krel"],
            "Collection's summaries[geoadmin:variant] has not been "
            "correctly updated after asset has been inserted."
        )
        self.assertCountEqual(
            self.collection.summaries_geoadmin_lang, ["en", "fr"],
            "Collection's summaries[geoadmin:lang] has not been "
            "correctly updated after asset has been inserted."
        )
        self.assertListEqual(
            self.collection.summaries_proj_epsg, [4321, 9999],
            "Collection's summaries[proj:epsg] has not been correctly "
            "updated after asset has been inserted."
        )

        col_asset1 = self.add_collection_asset(5678)
        col_asset1.proj_epsg = 8765
        col_asset1.full_clean()
        col_asset1.save()
        self.collection.refresh_from_db()

        self.assertCountEqual(
            self.collection.summaries_eo_gsd, [2.1, 12.34],
            "Collection's summaries[gsd] has not been correctly "
            "updated after asset has been inserted."
        )
        self.assertCountEqual(
            self.collection.summaries_geoadmin_variant, ["komb", "krel"],
            "Collection's summaries[geoadmin:variant] has not been "
            "correctly updated after asset has been inserted."
        )
        self.assertCountEqual(
            self.collection.summaries_geoadmin_lang, ["en", "fr"],
            "Collection's summaries[geoadmin:lang] has not been "
            "correctly updated after asset has been inserted."
        )
        self.assertCountEqual(
            self.collection.summaries_proj_epsg, [4321, 9999, 8765],
            "Collection's summaries[proj:epsg] has not been correctly "
            "updated after asset has been inserted."
        )

    def test_update_collection_summaries_none_values(self):
        # update a variant, that as been None as a start value
        item = self.data_factory.create_item_sample(collection=self.collection).model
        asset = self.add_asset(item, None, None, None, None)
        self.assertListEqual(self.collection.summaries_proj_epsg, [])
        self.assertListEqual(self.collection.summaries_geoadmin_variant, [])
        self.assertListEqual(self.collection.summaries_geoadmin_lang, [])
        self.assertListEqual(self.collection.summaries_eo_gsd, [])
        asset.geoadmin_variant = "krel"
        asset.eo_gsd = 2
        asset.proj_epsg = 2056
        asset.geoadmin_lang = 'rm'
        asset.full_clean()
        asset.save()

        self.collection.refresh_from_db()
        self.assertListEqual(self.collection.summaries_proj_epsg, [2056])
        self.assertListEqual(self.collection.summaries_eo_gsd, [2.0])
        self.assertListEqual(self.collection.summaries_geoadmin_variant, ['krel'])
        self.assertListEqual(self.collection.summaries_geoadmin_lang, ['rm'])

        col_asset = self.add_collection_asset(None)
        self.assertListEqual(self.collection.summaries_proj_epsg, [2056])
        self.assertListEqual(self.collection.summaries_eo_gsd, [2.0])
        self.assertListEqual(self.collection.summaries_geoadmin_variant, ['krel'])
        self.assertListEqual(self.collection.summaries_geoadmin_lang, ['rm'])
        col_asset.proj_epsg = 4102
        col_asset.full_clean()
        col_asset.save()

        self.collection.refresh_from_db()
        self.assertListEqual(self.collection.summaries_proj_epsg, [2056, 4102])
        self.assertListEqual(self.collection.summaries_eo_gsd, [2.0])
        self.assertListEqual(self.collection.summaries_geoadmin_variant, ['krel'])
        self.assertListEqual(self.collection.summaries_geoadmin_lang, ['rm'])

    def counter_values(self, count_model):
        return sorted(
            count_model.objects.filter(collection=self.collection).values_list('value', 'count'),
            key=str
        )

    def assert_counter_values(self, gsd, variant, epsg, lang):
        self.assertListEqual(self.counter_values(GSDCount), gsd)
        self.assertListEqual(self.counter_values(GeoadminVariantCount), variant)
        self.assertListEqual(self.counter_values(ProjEPSGCount), epsg)
        self.assertListEqual(self.counter_values(GeoadminLangCount), lang)

    def test_counter_tables_ignore_null_values_on_asset_insert(self):
        item = self.data_factory.create_item_sample(collection=self.collection).model
        self.add_asset(item, None, None, None, None)
        self.add_asset(item, None, None, None, None)
        self.add_asset(item, 2, 'krel', 2056, 'de')

        self.assert_counter_values(
            gsd=[(2.0, 1)], variant=[('krel', 1)], epsg=[(2056, 1)], lang=[('de', 1)]
        )

    def test_counter_tables_ignore_null_values_on_collection_asset_insert(self):
        self.add_collection_asset(None)
        self.add_collection_asset(None)

        self.assertListEqual(self.counter_values(ProjEPSGCount), [])

    def test_counter_tables_ignore_null_values_on_asset_update(self):
        item = self.data_factory.create_item_sample(collection=self.collection).model
        asset = self.add_asset(item, None, None, None, None)

        asset.eo_gsd = 2
        asset.geoadmin_variant = 'krel'
        asset.proj_epsg = 2056
        asset.geoadmin_lang = 'de'
        asset.full_clean()
        asset.save()
        self.assert_counter_values(
            gsd=[(2.0, 1)], variant=[('krel', 1)], epsg=[(2056, 1)], lang=[('de', 1)]
        )

        asset.eo_gsd = None
        asset.geoadmin_variant = None
        asset.proj_epsg = None
        asset.geoadmin_lang = None
        asset.full_clean()
        asset.save()
        self.assert_counter_values(gsd=[], variant=[], epsg=[], lang=[])

    def test_reset_counter_tables_ignores_null_values(self):
        item = self.data_factory.create_item_sample(collection=self.collection).model
        self.add_asset(item, None, None, None, None)
        self.add_asset(item, 2, 'krel', 2056, 'de')
        self.add_collection_asset(None)

        call_command('reset_counter_tables')

        self.assert_counter_values(
            gsd=[(2.0, 1)], variant=[('krel', 1)], epsg=[(2056, 1)], lang=[('de', 1)]
        )
