from datetime import timedelta
from io import StringIO
from unittest.mock import patch

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
        cls.setup_items_count = 1

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
    def setUp(self):
        super().setUp()
        self.items = []
        for i in range(self.setup_items_count):
            self.items.append(self.factory.create_item_sample(
                self.collection,
                name=f'item-{i}',
                db_create=True,
                properties_expires=timezone.now() + timedelta(hours=1)
            ))
        self.assets = []
        for item in self.items:
            self.assets.extend(self.factory.create_asset_samples(
                2, item.model, name=['asset-0.tiff', 'asset-1.tiff'], db_create=True
            ))

        self.out = None
        self.expected_output = "invalid output from test fixture"
        self.expect_deletions = None

    def assert_object_exists(self, cls, obj):
        class_name = type(cls).__name__
        obj_name = obj['name']
        self.assertTrue(
            cls.objects.filter(name=obj_name).exists(),
            msg=f"{class_name} unexpectedly absent: {obj_name}"
        )

    def assert_objects_exist(self, cls, objs):
        for obj in objs:
            self.assert_object_exists(cls, obj)

    def assert_object_does_not_exist(self, cls, obj):
        class_name = type(cls).__name__
        obj_name = obj['name']
        self.assertFalse(
            cls.objects.filter(name=obj_name).exists(),
            msg=f"{class_name} unexpectedly present: {obj_name}"
        )

    def assert_objects_do_not_exist(self, cls, objs):
        for obj in objs:
            self.assert_object_does_not_exist(cls, obj)

    def tearDown(self):
        self.assertEqual(self.expected_output, self.out)

        if self.expect_deletions is None:
            raise ValueError("self.expect_deletions was not set by the test")
        if self.expect_deletions:
            self.assert_objects_do_not_exist(Item, self.items)
            self.assert_objects_do_not_exist(Asset, self.assets)
        else:
            self.assert_objects_exist(Item, self.items)
            self.assert_objects_exist(Asset, self.assets)
        super().tearDown()

    def test_remove_item_dry_run(self):
        self.expected_output = """running command to remove expired items
deleting all items expired longer than 24 hours
skipping deletion of assets <QuerySet [<Asset: asset-0.tiff>, <Asset: asset-1.tiff>]>
skipping deletion of item collection-1/item-0
[dry run] would have removed 1 expired items
"""
        self.expect_deletions = False
        with patch.object(timezone, "now", return_value=timezone.now() + timedelta(hours=26)):
            self.out = self._call_command("--dry-run", "--no-color")

    def test_remove_item_no_expired_item(self):
        self.expected_output = """running command to remove expired items
deleting all items expired longer than 24 hours
successfully removed 0 expired items
"""
        self.expect_deletions = False
        self.out = self._call_command("--no-color")

    def test_remove_item(self):
        self.expected_output = """running command to remove expired items
deleting all items expired longer than 9 hours
deleted item item-0 and 2 assets belonging to it. extra={'item': 'item-0'}
successfully removed 1 expired items
"""
        self.expect_deletions = True
        with patch.object(timezone, "now", return_value=timezone.now() + timedelta(hours=10)):
            self.out = self._call_command("--min-age-hours=9", "--no-color")
