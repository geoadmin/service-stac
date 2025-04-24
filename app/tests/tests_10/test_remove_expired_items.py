import time
import tracemalloc
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from stac_api.management.commands.remove_expired_items import SafetyAbort
from stac_api.models.item import Asset
from stac_api.models.item import AssetUpload
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

    def make_asset_uploads(self, assets):
        asset_uploads = []
        for asset in assets:
            asset_uploads.append(
                AssetUpload(
                    asset=asset,
                    upload_id=f"upload-id-{asset.item.name}/{asset.name}",
                    checksum_multihash="this is a dummy sha256sum",
                    number_parts=1,
                    md5_parts="this is a dummy md5sum",
                    status=AssetUpload.Status.IN_PROGRESS
                )
            )
        return asset_uploads

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
        self.expiring_asset_uploads = self.make_asset_uploads(self.expiring_assets)
        self.remaining_asset_uploads = self.make_asset_uploads(self.remaining_assets)

        Item.objects.bulk_create(self.expiring_items + self.remaining_items)
        Asset.objects.bulk_create(self.expiring_assets + self.remaining_assets)
        AssetUpload.objects.bulk_create(self.expiring_asset_uploads + self.remaining_asset_uploads)

        self.stderr = StringIO()
        self.expected_stderr_patterns = None
        self.stdout = StringIO()
        self.expected_stdout_patterns = [
            "running command to remove expired items",
            (
                f"deleting no more than 110000 or 50% items expired for longer than"
                f" {self.expected_default_min_age_hours} hours"
            ),
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

    def assert_output_patterns(self, expected_patterns, actual):
        for pattern in expected_patterns:
            self.assertIn(pattern, actual)

    def assert_stdout(self):
        self.assert_output_patterns(self.expected_stdout_patterns, self.stdout.getvalue())

    def assert_stderr(self):
        output = self.stderr.getvalue()
        if self.expected_stderr_patterns is None:
            self.assertEqual('', output)
        else:
            self.assert_output_patterns(self.expected_stderr_patterns, output)

    def tearDown(self):
        self.assert_stderr()
        self.assert_stdout()
        self.assert_objects_existence()
        super().tearDown()

    def assert_objects_existence(self):
        self.assert_objects_do_not_exist(
            self.expiring_items + self.expiring_assets + self.expiring_asset_uploads
        )
        self.assert_objects_exist(
            self.remaining_items + self.remaining_assets + self.remaining_asset_uploads
        )

    def run_test(
        self,
        expected_stdout_patterns=None,
        expected_stderr_patterns=None,
        now_offset=None,
        command_args=None
    ):
        if now_offset is None:
            now_offset = self.expected_default_min_age_hours + self.expiring_deadline_hours
        if expected_stdout_patterns is not None:
            self.expected_stdout_patterns = expected_stdout_patterns
        if expected_stderr_patterns is not None:
            self.expected_stderr_patterns = expected_stderr_patterns
        if command_args is None:
            command_args = []
        with patch.object(
            timezone, "now", return_value=timezone.now() + timedelta(hours=now_offset)
        ):
            return self._call_command(*command_args, stdout=self.stdout, stderr=self.stderr)


class RemoveExpiredItems(RemoveExpiredItemsBase):

    def test_remove_item(self):
        self.run_test()

    def test_max_deletions_small(self):
        self.run_test(
            command_args=["--max-deletions=1"],
            expected_stdout_patterns=[
                "deleting no more than 1 or 50% items expired for longer than 24 hours"
            ]
        )


class RemoveExpiredItemsAll(RemoveExpiredItemsBase):

    def assert_objects_existence(self):
        self.assert_objects_do_not_exist(
            self.expiring_items + self.remaining_items + self.expiring_assets +
            self.remaining_assets + self.expiring_asset_uploads + self.remaining_asset_uploads
        )

    def test_remove_item_min_age_hours_shorter(self):
        self.run_test(
            command_args=["--min-age-hours=12", "--max-deletions-percentage=100"],
            expected_stdout_patterns=[
                "deleting no more than 110000 or 100% items expired for longer than 12 hours",
            ]
        )


class RemoveExpiredItemsNoDelete(RemoveExpiredItemsBase):

    def setUp(self):
        super().setUp()
        self.expected_stdout_patterns = []

    def assert_objects_existence(self):
        self.assert_objects_exist(
            self.expiring_items + self.remaining_items + self.expiring_assets +
            self.remaining_assets + self.expiring_asset_uploads + self.remaining_asset_uploads
        )

    def test_remove_item_dry_run(self):
        self.run_test(
            command_args=["--dry-run"],
            expected_stdout_patterns=[
                "running command to remove expired items",
                "deleting no more than 110000 or 50% items expired for longer than 24 hours",
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
            expected_stdout_patterns=[
                "running command to remove expired items",
                "deleting no more than 110000 or 50% items expired for longer than 30 hours",
                "successfully removed 0 expired items"
            ]
        )

    def test_min_age_hours_nan(self):
        self.assertRaisesRegex(
            CommandError,
            "--min-age-hours: invalid 'positive_int' value: 'NotANumber'",
            self.run_test,
            command_args=["--min-age-hours=NotANumber"]
        )

    def test_min_age_hours_negative(self):
        self.assertRaisesRegex(
            CommandError,
            "--min-age-hours: invalid 'positive_int' value: '-1'",
            self.run_test,
            command_args=["--min-age-hours=-1"]
        )

    def test_max_deletions_nan(self):
        self.assertRaisesRegex(
            CommandError,
            "--max-deletions: invalid 'positive_int' value: 'not-a-number1'",
            self.run_test,
            command_args=["--max-deletions=not-a-number1"]
        )

    def test_max_deletions_negative(self):
        self.assertRaisesRegex(
            CommandError,
            "--max-deletions: invalid 'positive_int' value: '-1'",
            self.run_test,
            command_args=["--max-deletions=-1"]
        )

    def test_max_deletions_exceeded(self):
        self.assertRaisesRegex(
            SafetyAbort,
            "Attempting to delete too many items: 1 > 0.",
            self.run_test,
            command_args=["--max-deletions=0"],
            expected_stderr_patterns=["Attempting to delete too many items: 1 > 0."]
        )

    def test_max_deletions_percentage_nan(self):
        self.assertRaisesRegex(
            CommandError,
            "--max-deletions-percentage: invalid 'percentage_int' value: 'not-a-number2'",
            self.run_test,
            command_args=["--max-deletions-percentage=not-a-number2"]
        )

    def test_max_deletions_percentage_negative(self):
        self.assertRaisesRegex(
            CommandError,
            "--max-deletions-percentage: invalid 'percentage_int' value: '-1'",
            self.run_test,
            command_args=["--max-deletions-percentage=-1"]
        )

    def test_max_deletions_percentage_over_100(self):
        self.assertRaisesRegex(
            CommandError,
            "--max-deletions-percentage: invalid 'percentage_int' value: '101'",
            self.run_test,
            command_args=["--max-deletions-percentage=101"]
        )

    def test_max_deletions_percentage_exceeded(self):
        self.assertRaisesRegex(
            SafetyAbort,
            "Attempting to delete too many items: 50.00% > 1%.",
            self.run_test,
            command_args=["--max-deletions-percentage=1"],
            expected_stderr_patterns="Attempting to delete too many items: 50.00% > 1%."
        )


class RemoveExpiredItemsManyWithProfiling(RemoveExpiredItemsBase):
    expiring_items_count = 1000
    remaining_items_count = 20

    def test_remove_item(self):
        self.run_test(command_args=["--max-deletions-percentage=99"], expected_stdout_patterns=[])

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
