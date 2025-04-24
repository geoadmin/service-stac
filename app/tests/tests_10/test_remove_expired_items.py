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


class RemoveExpiredItemsBase(TestCase):
    expiring_items_count = 1
    remaining_items_count = 1
    expiring_deadline_hours = 1
    expected_default_min_age_hours = 24

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

    def make_items(self, expiration, count, name_offset=0):
        items = []
        for i in range(count):
            items.append(
                self.factory.create_item_sample(
                    self.collection,
                    name=f'item-{i+name_offset}',
                    db_create=True,
                    properties_expires=expiration
                )
            )
        return items

    def make_assets(self, items, count=2):
        assets = []
        for item in items:
            assets.extend(
                self.factory.create_asset_samples(
                    count, item.model, name=['asset-0.tiff', 'asset-1.tiff'], db_create=True
                )
            )
        return assets

    @mock_s3_asset_file
    def setUp(self):
        super().setUp()

        expiration = timezone.now() + timedelta(hours=self.expiring_deadline_hours)
        self.expiring_items = self.make_items(expiration, self.expiring_items_count, name_offset=0)
        self.remaining_items = self.make_items(
            expiration + timedelta(hours=1), self.remaining_items_count, self.expiring_items_count
        )
        self.expiring_assets = self.make_assets(self.expiring_items)
        self.remaining_assets = self.make_assets(self.remaining_items)

        self.out = None
        self.expected_output_patterns = [
            "running command to remove expired items",
            f"deleting all items expired longer than {self.expected_default_min_age_hours} hours",
            f"successfully removed {self.expiring_items_count} expired items",
        ]
        for i in range(self.expiring_items_count):
            self.expected_output_patterns.append(
                f"deleted item item-{i} and 2 assets belonging to it. extra={{'item': 'item-{i}'}}"
            )

    def assert_object_exists(self, cls, obj):
        class_name = cls.__name__
        obj_name = obj['name']
        self.assertTrue(
            cls.objects.contains(obj.model), msg=f"{class_name} unexpectedly absent: {obj_name}"
        )

    def assert_objects_exist(self, cls, objs):
        for obj in objs:
            self.assert_object_exists(cls, obj)

    def assert_object_does_not_exist(self, cls, obj):
        class_name = cls.__name__
        obj_name = obj['name']
        self.assertFalse(
            cls.objects.contains(obj.model), msg=f"{class_name} unexpectedly present: {obj_name}"
        )

    def assert_objects_do_not_exist(self, cls, objs):
        for obj in objs:
            self.assert_object_does_not_exist(cls, obj)

    def tearDown(self):
        for pattern in self.expected_output_patterns:
            self.assertIn(pattern, self.out)
        self.assert_objects_existence()
        super().tearDown()

    def assert_objects_existence(self):
        self.assert_objects_do_not_exist(Item, self.expiring_items)
        self.assert_objects_do_not_exist(Asset, self.expiring_assets)
        self.assert_objects_exist(Item, self.remaining_items)
        self.assert_objects_exist(Asset, self.remaining_assets)

    def run_test(self, expected_output_patterns=None, now_offset=None, command_args=None):
        if now_offset is None:
            now_offset = self.expected_default_min_age_hours + self.expiring_deadline_hours
        if expected_output_patterns is not None:
            self.expected_output_patterns = expected_output_patterns
        if command_args is None:
            command_args = []
        with patch.object(
            timezone, "now", return_value=timezone.now() + timedelta(hours=now_offset)
        ):
            self.out = self._call_command(*command_args)


class RemoveExpiredItems(RemoveExpiredItemsBase):

    def test_remove_item(self):
        self.run_test()


class RemoveExpiredItemsNoDelete(RemoveExpiredItemsBase):

    def assert_objects_existence(self):
        self.assert_objects_exist(Item, self.expiring_items + self.remaining_items)
        self.assert_objects_exist(Asset, self.expiring_assets + self.remaining_assets)

    def test_remove_item_dry_run(self):
        self.run_test(
            command_args=["--dry-run"],
            expected_output_patterns=[
                "running command to remove expired items",
                "deleting all items expired longer than 24 hours",
                (
                    "skipping deletion of assets <QuerySet"
                    " [<Asset: asset-0.tiff>, <Asset: asset-1.tiff>]>"
                ),
                "skipping deletion of item collection-1/item-0",
                "[dry run] would have removed 1 expired items",
            ]
        )

    def test_remove_item_no_expired_item(self):
        self.run_test(
            command_args=["--min-age-hours=30"],
            expected_output_patterns=[
                "running command to remove expired items",
                "deleting all items expired longer than 30 hours",
                "successfully removed 0 expired items"
            ]
        )


class RemoveExpiredItemsMany(RemoveExpiredItemsBase):
    expiring_items_count = 10
    remaining_items_count = 10

    def test_remove_item(self):
        self.run_test()
