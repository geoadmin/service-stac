from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from stac_api.models.item import Asset
from stac_api.models.item import Item

from tests.tests_10.data_factory import Factory
from tests.utils import MockS3PerTestMixin


class SetThumbnailRoleTestCase(MockS3PerTestMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model

    def _call_command(self, *args, **kwargs):
        return call_command(
            "set_thumbnail_role",
            *args,
            **kwargs,
        )

    def make_item(self, name):
        item = Item(collection=self.collection, name=name)
        item.save()
        return item

    def setUp(self):
        super().setUp()

        self.item = self.make_item('item-1')
        self.item_with_existing_role = self.make_item('item-2')

        # Assets without any role set, matching the thumbnail names, should be updated.
        self.thumbnail_png_no_role = Asset(item=self.item, name='thumbnail.png', roles=None)
        self.thumbnail_jpg_no_role = Asset(item=self.item, name='thumbnail.jpg', roles=None)

        # An asset that already has roles set should not be touched, even though its name
        # matches. Placed on a separate item to avoid violating the unique name constraint.
        self.thumbnail_png_with_role = Asset(
            item=self.item_with_existing_role, name='thumbnail.png', roles=['other']
        )

        # Assets with a name that doesn't match should not be touched, regardless of role.
        self.other_asset_no_role = Asset(item=self.item, name='other-asset.tiff', roles=None)
        self.other_asset_with_role = Asset(
            item=self.item, name='other-asset-2.tiff', roles=['data']
        )

        Asset.objects.bulk_create([
            self.thumbnail_png_no_role,
            self.thumbnail_jpg_no_role,
            self.thumbnail_png_with_role,
            self.other_asset_no_role,
            self.other_asset_with_role,
        ])

        self.stderr = StringIO()
        self.stdout = StringIO()

    def assert_stdout_patterns(self, patterns):
        output = self.stdout.getvalue()
        for pattern in patterns:
            self.assertIn(pattern, output)

    def assert_no_stderr(self):
        self.assertEqual('', self.stderr.getvalue())

    def run_command(self, *args):
        return self._call_command(*args, stdout=self.stdout, stderr=self.stderr)

    def test_set_thumbnail_role_updates_matching_assets_without_role(self):
        self.run_command()

        self.thumbnail_png_no_role.refresh_from_db()
        self.thumbnail_jpg_no_role.refresh_from_db()
        self.assertEqual(['thumbnail'], self.thumbnail_png_no_role.roles)
        self.assertEqual(['thumbnail'], self.thumbnail_jpg_no_role.roles)

        self.assert_no_stderr()
        self.assert_stdout_patterns([
            "running command to set asset thumbnail roles",
            "successfully updated roles for 2 thumbnail assets",
        ])

    def test_set_thumbnail_role_does_not_touch_asset_with_existing_role(self):
        self.run_command()

        self.thumbnail_png_with_role.refresh_from_db()
        self.assertEqual(['other'], self.thumbnail_png_with_role.roles)

    def test_set_thumbnail_role_does_not_touch_non_matching_assets(self):
        self.run_command()

        self.other_asset_no_role.refresh_from_db()
        self.other_asset_with_role.refresh_from_db()
        self.assertIsNone(self.other_asset_no_role.roles)
        self.assertEqual(['data'], self.other_asset_with_role.roles)

    def test_set_thumbnail_role_no_matching_assets(self):
        Asset.objects.filter(name__in=['thumbnail.png', 'thumbnail.jpg']
                            ).update(roles=['thumbnail'])

        self.run_command()

        self.assert_no_stderr()
        self.assert_stdout_patterns([
            "running command to set asset thumbnail roles",
            "successfully updated roles for 0 thumbnail assets",
        ])
