import logging

from django.core.exceptions import ValidationError
from django.test import TestCase

from stac_api.models import Asset
from stac_api.models import Collection

from tests.data_factory import Factory
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)


class AssetsModelTestCase(TestCase):

    @classmethod
    @mock_s3_asset_file
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample(db_create=True).model
        cls.item = cls.factory.create_item_sample(
            collection=Collection.objects.get(name="collection-1"), db_create=True
        ).model
        cls.asset = cls.factory.create_asset_sample(
            item=cls.item, db_create=True, create_asset_file=False
        )

    @mock_s3_asset_file
    def test_create_already_existing_asset(self):
        # try to create already existing asset twice
        with self.assertRaises(ValidationError, msg="Existing asset could be re-created."):
            asset = Asset(**self.asset.attributes)
            asset.full_clean()
            asset.save()

    def test_create_asset_invalid_name(self):
        #     # try to create a asset with invalid asset name and other invalid fields
        with self.assertRaises(ValidationError, msg="asset with invalid name was accepted."):
            asset_data = self.factory.create_asset_sample(
                item=self.item, sample="asset-invalid", create_asset_file=False
            )
            asset = Asset(**asset_data.attributes)
            asset.full_clean()
            asset.save()

    def test_create_asset_missing_mandatory_fields(self):
        # try to create a asset with missing mandatory attributes.
        with self.assertRaises(
            ValidationError, msg="asset with missing mandatory fields was accepted."
        ):
            self.factory.create_asset_sample(
                item=self.item,
                sample="asset-missing-required",
                db_create=True,
                create_asset_file=False
            )

    def test_create_asset_valid_geoadmin_variant(self):
        # try to create a asset with valid geoadmin variant. This should not raise any error.
        self.factory.create_asset_sample(
            item=self.item,
            sample="asset-valid-geoadmin-variant",
            db_create=True,
            create_asset_file=False
        )

    def test_create_asset_invalid_geoadmin_variant(self):
        # try to create a asset with invalid geoadmin variant.
        with self.assertRaises(ValidationError, msg="asset with invalid geoadmin variant."):
            self.factory.create_asset_sample(
                item=self.item,
                sample="asset-invalid-geoadmin-variant",
                db_create=True,
                create_asset_file=False
            )
