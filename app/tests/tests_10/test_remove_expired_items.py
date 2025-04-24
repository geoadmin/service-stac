import time
import tracemalloc
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
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
        return call_command(
            "remove_expired_items",
            *args,
            **kwargs,
        )

    def make_items(self, expiration, count, name_offset=0):
        items = []
        for i in range(count):
            items.append(
                Item(
                    collection=self.collection,
                    name=f'item-{i+name_offset}',
                    properties_expires=expiration
                )
            )
        return items

    def make_assets(self, items, count=2):
        assets = []
        for item in items:
            for i in range(count):
                assets.append(Asset(item=item, name=f'asset-{i}.tiff'))
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

        Item.objects.bulk_create(self.expiring_items + self.remaining_items)
        Asset.objects.bulk_create(self.expiring_assets + self.remaining_assets)

        self.stdout = StringIO()
        self.stderr = StringIO()
        self.expected_output_patterns = [
            "running command to remove expired items",
            f"deleting all items expired longer than {self.expected_default_min_age_hours} hours",
            f"successfully removed {self.expiring_items_count} expired items",
        ]

    def assert_object_exists(self, obj):
        cls = obj.__class__
        self.assertTrue(cls.objects.contains(obj), msg=f"{cls.__name__} unexpectedly absent: {obj}")

    def assert_objects_exist(self, objs):
        for obj in objs:
            self.assert_object_exists(obj)

    def assert_object_does_not_exist(self, obj):
        cls = obj.__class__
        self.assertFalse(
            cls.objects.contains(obj), msg=f"{cls.__name__} unexpectedly present: {obj}"
        )

    def assert_objects_do_not_exist(self, objs):
        for obj in objs:
            self.assert_object_does_not_exist(obj)

    def tearDown(self):
        output = self.stdout.getvalue()
        for pattern in self.expected_output_patterns:
            self.assertIn(pattern, output)
        self.assertEqual('', self.stderr.getvalue())
        self.assert_objects_existence()
        super().tearDown()

    def assert_objects_existence(self):
        self.assert_objects_do_not_exist(self.expiring_items + self.expiring_assets)
        self.assert_objects_exist(self.remaining_items + self.remaining_assets)

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
            return self._call_command(*command_args, stdout=self.stdout, stderr=self.stderr)


class RemoveExpiredItems(RemoveExpiredItemsBase):

    def test_remove_item(self):
        self.run_test()


class RemoveExpiredItemsAll(RemoveExpiredItemsBase):

    def assert_objects_existence(self):
        self.assert_objects_do_not_exist(
            self.expiring_items + self.remaining_items + self.expiring_assets +
            self.remaining_assets
        )

    def test_remove_item_min_age_hours_shorter(self):
        self.run_test(
            command_args=["--min-age-hours=12"],
            expected_output_patterns=[
                "deleting all items expired longer than 12 hours",
            ]
        )


class RemoveExpiredItemsNoDelete(RemoveExpiredItemsBase):

    def assert_objects_existence(self):
        self.assert_objects_exist(
            self.expiring_items + self.remaining_items + self.expiring_assets +
            self.remaining_assets
        )

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
                "skipping deletion of items <ItemQuerySet [<Item: collection-1/item-0>]>",
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

    def test_min_age_hours_nan(self):
        self.assertRaisesRegex(
            CommandError,
            "--min-age-hours: invalid int value: 'NotANumber'",
            self.run_test,
            expected_output_patterns=[],
            command_args=["--min-age-hours=NotANumber"]
        )


class RemoveExpiredItemsManyWithProfiling(RemoveExpiredItemsBase):
    expiring_items_count = 1000
    remaining_items_count = 10

    def test_remove_item(self):
        self.run_test()

    @staticmethod
    def _diff_memory(before, after):
        diff = after.compare_to(before, 'filename')
        total = 0
        for d in diff:
            total += d.size_diff
        return total

    def _call_command(self, *args, **kwargs):
        tracemalloc.start()
        mem_before = tracemalloc.take_snapshot()

        time_before = time.time_ns()

        retval = super()._call_command(*args, **kwargs)

        time_after = time.time_ns()

        mem_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        time_consumed = (time_after - time_before) / 10**9
        mem_consumed = self._diff_memory(mem_before, mem_after)
        print(
            f"memory consumed: {mem_consumed} ({mem_consumed/self.expiring_items_count} per item)"
        )
        print(
            f"time consumed: {time_consumed}s ({time_consumed/self.expiring_items_count} per item)"
        )

        return retval
