import logging
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase
from django.test import TransactionTestCase

from stac_api.models import Asset
from stac_api.models import AssetUpload
from stac_api.utils import get_sha256_multihash
from stac_api.utils import utc_aware

from tests.data_factory import Factory
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)


class AssetUploadTestCaseMixin:

    def create_asset_upload(self, asset, upload_id, **kwargs):
        asset_upload = AssetUpload(
            asset=asset,
            upload_id=upload_id,
            checksum_multihash=get_sha256_multihash(b'Test'),
            number_parts=1,
            **kwargs
        )
        asset_upload.full_clean()
        asset_upload.save()
        self.assertEqual(
            asset_upload,
            AssetUpload.objects.get(
                upload_id=upload_id,
                asset__name=asset.name,
                asset__item__name=asset.item.name,
                asset__item__collection__name=asset.item.collection.name
            )
        )
        return asset_upload

    def update_asset_upload(self, asset_upload, **kwargs):
        for kwarg, value in kwargs.items():
            setattr(asset_upload, kwarg, value)
        asset_upload.full_clean()
        asset_upload.save()
        asset_upload.refresh_from_db()
        self.assertEqual(
            asset_upload,
            AssetUpload.objects.get(
                upload_id=asset_upload.upload_id, asset__name=asset_upload.asset.name
            )
        )
        return asset_upload

    def check_etag(self, etag):
        self.assertIsInstance(etag, str, msg="Etag must be a string")
        self.assertNotEqual(etag, '', msg='Etag should not be empty')


class AssetUploadModelTestCase(TestCase, AssetUploadTestCaseMixin):

    @classmethod
    @mock_s3_asset_file
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.item = cls.factory.create_item_sample(collection=cls.collection).model
        cls.asset_1 = cls.factory.create_asset_sample(item=cls.item).model
        cls.asset_2 = cls.factory.create_asset_sample(item=cls.item).model

    def test_create_asset_upload_default(self):
        asset_upload = self.create_asset_upload(self.asset_1, 'default-upload')
        self.assertEqual(asset_upload.urls, [], msg="Wrong default value")
        self.assertEqual(asset_upload.ended, None, msg="Wrong default value")
        self.assertAlmostEqual(
            utc_aware(datetime.utcnow()).timestamp(),
            asset_upload.created.timestamp(),
            delta=1,
            msg="Wrong default value"
        )

    def test_unique_constraint(self):
        # Check that asset upload is unique in collection/item/asset
        # therefore the following asset upload should be ok
        # collection-1/item-1/asset-1/default-upload
        # collection-2/item-1/asset-1/default-upload
        collection_2 = self.factory.create_collection_sample().model
        item_2 = self.factory.create_item_sample(collection_2, name=self.item.name).model
        asset_2 = self.factory.create_asset_sample(item_2, name=self.asset_1.name).model
        asset_upload_1 = self.create_asset_upload(self.asset_1, 'default-upload')
        asset_upload_2 = self.create_asset_upload(asset_2, 'default-upload')
        self.assertEqual(asset_upload_1.upload_id, asset_upload_2.upload_id)
        self.assertEqual(asset_upload_1.asset.name, asset_upload_2.asset.name)
        self.assertEqual(asset_upload_1.asset.item.name, asset_upload_2.asset.item.name)
        self.assertNotEqual(
            asset_upload_1.asset.item.collection.name, asset_upload_2.asset.item.collection.name
        )
        # But duplicate path are not allowed
        with self.assertRaises(ValidationError, msg="Existing asset upload could be re-created."):
            asset_upload_3 = self.create_asset_upload(self.asset_1, 'default-upload')

    def test_create_asset_upload_duplicate_in_progress(self):
        # create a first upload on asset 1
        asset_upload_1 = self.create_asset_upload(self.asset_1, '1st-upload')

        # create a first upload on asset 2
        asset_upload_2 = self.create_asset_upload(self.asset_2, '1st-upload')

        # create a second upload on asset 1 should not be allowed.
        with self.assertRaises(
            IntegrityError, msg="Existing asset upload already in progress could be re-created."
        ):
            asset_upload_3 = self.create_asset_upload(self.asset_1, '2nd-upload')

    def test_asset_upload_etag(self):
        asset_upload = self.create_asset_upload(self.asset_1, 'default-upload')
        original_etag = asset_upload.etag
        self.check_etag(original_etag)
        asset_upload = self.update_asset_upload(asset_upload, status=AssetUpload.Status.ABORTED)
        self.check_etag(asset_upload.etag)
        self.assertNotEqual(asset_upload.etag, original_etag, msg='Etag was not updated')

    def test_asset_upload_invalid_number_parts(self):
        with self.assertRaises(ValidationError):
            asset_upload = AssetUpload(
                asset=self.asset_1,
                upload_id='my-upload-id',
                checksum_multihash=get_sha256_multihash(b'Test'),
                number_parts=-1
            )
            asset_upload.full_clean()
            asset_upload.save()


class AssetUploadDeleteProtectModelTestCase(TransactionTestCase, AssetUploadTestCaseMixin):

    @mock_s3_asset_file
    def setUp(self):
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection,).model
        self.asset = self.factory.create_asset_sample(item=self.item).model

    def test_delete_asset_upload(self):
        upload_id = 'upload-in-progress'
        asset_upload = self.create_asset_upload(self.asset, upload_id)

        with self.assertRaises(ProtectedError, msg="Deleting an upload in progress not allowed"):
            asset_upload.delete()

        asset_upload = self.update_asset_upload(
            asset_upload, status=AssetUpload.Status.COMPLETED, ended=utc_aware(datetime.utcnow())
        )

        asset_upload.delete()
        self.assertFalse(
            AssetUpload.objects.all().filter(upload_id=upload_id,
                                             asset__name=self.asset.name).exists()
        )

    def test_delete_asset_with_upload_in_progress(self):
        asset_upload_1 = self.create_asset_upload(self.asset, 'upload-in-progress')
        asset_upload_2 = self.create_asset_upload(
            self.asset,
            'upload-completed',
            status=AssetUpload.Status.COMPLETED,
            ended=utc_aware(datetime.utcnow())
        )
        asset_upload_3 = self.create_asset_upload(
            self.asset,
            'upload-aborted',
            status=AssetUpload.Status.ABORTED,
            ended=utc_aware(datetime.utcnow())
        )
        asset_upload_4 = self.create_asset_upload(
            self.asset,
            'upload-aborted-2',
            status=AssetUpload.Status.ABORTED,
            ended=utc_aware(datetime.utcnow())
        )

        # Try to delete parent asset
        with self.assertRaises(ValidationError):
            self.asset.delete()
        self.assertEqual(4, len(list(AssetUpload.objects.all())))
        self.assertTrue(
            Asset.objects.all().filter(
                name=self.asset.name,
                item__name=self.item.name,
                item__collection__name=self.collection.name
            ).exists()
        )

        self.update_asset_upload(
            asset_upload_1, status=AssetUpload.Status.ABORTED, ended=utc_aware(datetime.utcnow())
        )

        self.asset.delete()
        self.assertEqual(0, len(list(AssetUpload.objects.all())))
        self.assertFalse(
            Asset.objects.all().filter(
                name=self.asset.name,
                item__name=self.item.name,
                item__collection__name=self.collection.name
            ).exists()
        )
