import logging

from django.core.exceptions import ValidationError

from stac_api.models import CollectionAsset

from tests.tests_10.base_test import StacBaseTransactionTestCase
from tests.tests_10.data_factory import Factory
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)


class CollectionAssetsModelTestCase(StacBaseTransactionTestCase):

    @mock_s3_asset_file
    def setUp(self):
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample(db_create=True).model
        self.asset = self.factory.create_collection_asset_sample(
            collection=self.collection, db_create=True
        )

    def test_create_already_existing_asset(self):
        # try to create already existing asset twice
        with self.assertRaises(ValidationError, msg="Existing asset could be re-created."):
            asset = CollectionAsset(**self.asset.attributes)
            asset.full_clean()
            asset.save()

    def test_create_asset_invalid_name(self):
        # try to create a asset with invalid asset name and other invalid fields
        with self.assertRaises(ValidationError, msg="asset with invalid name was accepted."):
            self.factory.create_collection_asset_sample(
                collection=self.collection, sample="asset-invalid", db_create=True
            )
            # db_create=True implicitly creates the asset file.
            # That's why it is used here and in the following tests

    def test_create_asset_missing_mandatory_fields(self):
        # try to create an asset with missing mandatory attributes.
        with self.assertRaises(
            ValidationError, msg="asset with missing mandatory fields was accepted."
        ):
            self.factory.create_collection_asset_sample(
                collection=self.collection,
                sample="asset-missing-required",
                db_create=True,
            )

    def test_create_update_asset_invalid_media_type(self):
        # try to create an asset with invalid media type
        with self.assertRaises(
            ValidationError, msg="asset with invalid media type was accepted."
        ) as context:
            self.factory.create_collection_asset_sample(
                collection=self.collection,
                name='my-asset.yaml',
                media_type="application/vnd.oai.openapi+yaml;version=3.0",
                db_create=True,
            )
        exception = context.exception
        self.assertIn(
            "Invalid id extension '.yaml', id must have a valid file extension", exception.messages
        )
        self.assertIn(
            "Value 'application/vnd.oai.openapi+yaml;version=3.0' is not a valid choice.",
            exception.messages
        )
        self.assertIn(
            'Invalid media type "application/vnd.oai.openapi+yaml;version=3.0"', exception.messages
        )

        with self.assertRaises(
            ValidationError, msg="asset with name missmatch media type was accepted."
        ) as context:
            self.factory.create_collection_asset_sample(
                collection=self.collection,
                name='my-asset.txt',
                media_type="application/json",
                db_create=True,
            )
        exception = context.exception
        self.assertIn(
            "Invalid id extension '.txt', id must match its media type application/json",
            exception.messages
        )

        # Test invalid media type/name update
        asset = self.factory.create_collection_asset_sample(
            collection=self.collection, name='asset.xml', media_type='application/gml+xml'
        ).model
        with self.assertRaises(
            ValidationError, msg="asset with name missmatch media type was accepted."
        ) as context:
            asset.name = 'asset.zip'
            asset.full_clean()
            asset.save()
        asset.refresh_from_db()
        exception = context.exception
        self.assertIn(
            "Invalid id extension '.zip', id must match its media type application/gml+xml",
            exception.messages
        )
        with self.assertRaises(
            ValidationError, msg="asset with name missmatch media type was accepted."
        ) as context:
            asset.media_type = 'text/plain'
            asset.full_clean()
            asset.save()
        asset.refresh_from_db()
        exception = context.exception
        self.assertIn(
            "Invalid id extension '.xml', id must match its media type text/plain",
            exception.messages
        )
        with self.assertRaises(
            ValidationError, msg="asset with name missmatch media type was accepted."
        ) as context:
            asset.media_type = 'invalid/media-type'
            asset.full_clean()
            asset.save()
        asset.refresh_from_db()
        exception = context.exception
        self.assertIn("Value 'invalid/media-type' is not a valid choice.", exception.messages)

    def test_create_asset_media_type_validation(self):
        # try to create an asset of media type with several extensions
        self.factory.create_collection_asset_sample(
            collection=self.collection,
            name='asset.xml',
            media_type='application/gml+xml',
            db_create=True
        )
        self.factory.create_collection_asset_sample(
            collection=self.collection,
            name='asset.gml',
            media_type='application/gml+xml',
            db_create=True
        )

    def test_create_update_asset_media_type_validation(self):
        # try to create an asset of media type with several extensions
        asset = self.factory.create_collection_asset_sample(
            collection=self.collection, name='asset.xml', media_type='application/gml+xml'
        ).model

        # correct the extension
        asset.name = 'asset.gml'
        asset.full_clean()
        asset.save()
        self.assertEqual(CollectionAsset.objects.get(pk=asset.pk).name, asset.name)

        # Change media type with same extension
        asset = self.factory.create_collection_asset_sample(
            collection=self.collection, name='asset.xml', media_type='application/gml+xml'
        ).model
        asset.media_type = 'application/x.interlis; version=2.3'
        asset.full_clean()
        asset.save()
        self.assertEqual(CollectionAsset.objects.get(pk=asset.pk).media_type, asset.media_type)

        # Change media type and extension
        asset = self.factory.create_collection_asset_sample(
            collection=self.collection, name='asset.json', media_type='application/json'
        ).model
        asset.name = 'asset.zip'
        asset.media_type = 'text/x.plain+zip'
        asset.full_clean()
        asset.save()
        _asset = CollectionAsset.objects.get(pk=asset.pk)
        self.assertEqual(_asset.name, asset.name)
        self.assertEqual(_asset.media_type, asset.media_type)
