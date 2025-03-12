import time
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from stac_api.models.item import Asset
from stac_api.models.item import Item

from tests.tests_10.data_factory import Factory
from tests.utils import mock_s3_asset_file


class RemoveExpiredItems(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model

    def _call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "remove_expired_items",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )
        return out.getvalue()

    @mock_s3_asset_file
    def test_remove_item_dry_run(self):
        item_0 = self.factory.create_item_sample(
            self.collection,
            name='item-0',
            db_create=True,
            properties_expires=timezone.now() + timedelta(milliseconds=50)
        )
        assets = self.factory.create_asset_samples(
            2, item_0.model, name=['asset-0.tiff', 'asset-1.tiff'], db_create=True
        )
        min_age_hours = 1 / 60 / 60 / 1000  # = 1ms
        time.sleep(min_age_hours * 100)
        out = self._call_command("--dry-run", "--no-color", f"--min-age-hours={min_age_hours}")
        self.assertEqual(
            out,
            f"""running command to remove expired items
deleting all items expired longer than {min_age_hours} hours
skipping deletion of assets <QuerySet [<Asset: asset-0.tiff>, <Asset: asset-1.tiff>]>
skipping deletion of item collection-1/item-0
[dry run] would have removed 1 expired items
"""
        )

        self.assertTrue(
            Item.objects.filter(name=item_0['name']).exists(),
            msg="Item has been deleted by dry run"
        )
        self.assertTrue(
            Asset.objects.filter(name=assets[0]['name']).exists(),
            msg="Asset has been deleted by dry run"
        )
        self.assertTrue(
            Asset.objects.filter(name=assets[1]['name']).exists(),
            msg="Asset has been deleted by dry run"
        )

    @mock_s3_asset_file
    def test_remove_item(self):
        item_1 = self.factory.create_item_sample(
            self.collection,
            name='item-1',
            db_create=True,
            properties_expires=timezone.now() + timedelta(milliseconds=50)
        )
        assets = self.factory.create_asset_samples(
            2, item_1.model, name=['asset-2.tiff', 'asset-3.tiff'], db_create=True
        )
        min_age_hours = 1.0
        out = self._call_command("--no-color", f"--min-age-hours={min_age_hours}")
        self.assertEqual(
            out,
            f"""running command to remove expired items
deleting all items expired longer than {min_age_hours} hours
successfully removed 0 expired items
"""
        )

        self.assertTrue(
            Item.objects.filter(name=item_1['name']).exists(),
            msg="not expired item has been deleted"
        )
        self.assertTrue(
            Asset.objects.filter(name=assets[0]['name']).exists(),
            msg="not expired asset has been deleted"
        )
        self.assertTrue(
            Asset.objects.filter(name=assets[1]['name']).exists(),
            msg="not expired asset has been deleted"
        )

        min_age_hours = 1 / 60 / 60 / 1000  # = 1ms
        time.sleep(min_age_hours * 100)
        out = self._call_command(f"--min-age-hours={min_age_hours}", "--no-color")
        self.assertEqual(
            out,
            f"""running command to remove expired items
deleting all items expired longer than {min_age_hours} hours
deleted item item-1 and 2 assets belonging to it. extra={{'item': 'item-1'}}
successfully removed 1 expired items
"""
        )
        self.assertFalse(
            Item.objects.filter(name=item_1['name']).exists(), msg="Expired item was not deleted"
        )
        self.assertFalse(
            Asset.objects.filter(name=assets[0]['name']).exists(),
            msg="Asset of expired item was not deleted"
        )
        self.assertFalse(
            Asset.objects.filter(name=assets[1]['name']).exists(),
            msg="Asset of expired item was not deleted"
        )
