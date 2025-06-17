import logging
from datetime import UTC
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase
from django.test import TransactionTestCase

from stac_api.models.collection import CollectionAsset
from stac_api.models.collection import CollectionAssetUpload
from stac_api.utils import get_sha256_multihash

from tests.tests_10.data_factory import Factory
from tests.utils import MockS3PerClassMixin

logger = logging.getLogger(__name__)


class CollectionAssetUploadTestCaseMixin:

    def create_asset_upload(self, asset, upload_id, **kwargs):
        asset_upload = CollectionAssetUpload(
            asset=asset,
            upload_id=upload_id,
            checksum_multihash=get_sha256_multihash(b'Test'),
            number_parts=1,
            md5_parts=["this is an md5 value"],
            **kwargs
        )
        asset_upload.full_clean()
        asset_upload.save()
        self.assertEqual(
            asset_upload,
            CollectionAssetUpload.objects.get(
                upload_id=upload_id,
                asset__name=asset.name,
                asset__collection__name=asset.collection.name
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
            CollectionAssetUpload.objects.get(
                upload_id=asset_upload.upload_id, asset__name=asset_upload.asset.name
            )
        )
        return asset_upload

    def check_etag(self, etag):
        self.assertIsInstance(etag, str, msg="Etag must be a string")
        self.assertNotEqual(etag, '', msg='Etag should not be empty')


class CollectionAssetUploadModelTestCase(
    CollectionAssetUploadTestCaseMixin, MockS3PerClassMixin, TestCase
):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.asset_1 = cls.factory.create_collection_asset_sample(collection=cls.collection).model
        cls.asset_2 = cls.factory.create_collection_asset_sample(collection=cls.collection).model

    def test_create_asset_upload_default(self):
        asset_upload = self.create_asset_upload(self.asset_1, 'default-upload')
        self.assertEqual(asset_upload.urls, [], msg="Wrong default value")
        self.assertEqual(asset_upload.ended, None, msg="Wrong default value")
        self.assertAlmostEqual(
            datetime.now(UTC).timestamp(),
            asset_upload.created.timestamp(),  # pylint: disable=no-member
            delta=1,
            msg="Wrong default value"
        )

    def test_unique_constraint(self):
        # Check that asset upload is unique in collection/asset
        # therefore the following asset upload should be ok
        # collection-1/asset-1/default-upload
        # collection-2/asset-1/default-upload
        collection_2 = self.factory.create_collection_sample().model
        asset_2 = self.factory.create_collection_asset_sample(
            collection_2, name=self.asset_1.name
        ).model
        asset_upload_1 = self.create_asset_upload(self.asset_1, 'default-upload')
        asset_upload_2 = self.create_asset_upload(asset_2, 'default-upload')
        self.assertEqual(asset_upload_1.upload_id, asset_upload_2.upload_id)
        self.assertEqual(asset_upload_1.asset.name, asset_upload_2.asset.name)
        self.assertNotEqual(
            asset_upload_1.asset.collection.name, asset_upload_2.asset.collection.name
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
            ValidationError, msg="Existing asset upload already in progress could be re-created."
        ):
            asset_upload_3 = self.create_asset_upload(self.asset_1, '2nd-upload')

    def test_asset_upload_etag(self):
        asset_upload = self.create_asset_upload(self.asset_1, 'default-upload')
        original_etag = asset_upload.etag
        self.check_etag(original_etag)
        asset_upload = self.update_asset_upload(
            asset_upload, status=CollectionAssetUpload.Status.ABORTED
        )
        self.check_etag(asset_upload.etag)
        self.assertNotEqual(asset_upload.etag, original_etag, msg='Etag was not updated')

    def test_asset_upload_invalid_number_parts(self):
        with self.assertRaises(ValidationError):
            asset_upload = CollectionAssetUpload(
                asset=self.asset_1,
                upload_id='my-upload-id',
                checksum_multihash=get_sha256_multihash(b'Test'),
                number_parts=-1,
                md5_parts=['fake_md5']
            )
            asset_upload.full_clean()
            asset_upload.save()


class CollectionAssetUploadDeleteProtectModelTestCase(
    CollectionAssetUploadTestCaseMixin, MockS3PerClassMixin, TransactionTestCase
):

    def setUp(self):
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.asset = self.factory.create_collection_asset_sample(collection=self.collection).model

    def test_delete_asset_upload(self):
        upload_id = 'upload-in-progress'
        asset_upload = self.create_asset_upload(self.asset, upload_id)

        with self.assertRaises(ProtectedError, msg="Deleting an upload in progress not allowed"):
            asset_upload.delete()

        asset_upload = self.update_asset_upload(
            asset_upload, status=CollectionAssetUpload.Status.COMPLETED, ended=datetime.now(UTC)
        )

        asset_upload.delete()
        self.assertFalse(
            CollectionAssetUpload.objects.all().filter(
                upload_id=upload_id, asset__name=self.asset.name
            ).exists()
        )

    def test_delete_asset_with_upload_in_progress(self):
        asset_upload_1 = self.create_asset_upload(self.asset, 'upload-in-progress')
        asset_upload_2 = self.create_asset_upload(
            self.asset,
            'upload-completed',
            status=CollectionAssetUpload.Status.COMPLETED,
            ended=datetime.now(UTC)
        )
        asset_upload_3 = self.create_asset_upload(
            self.asset,
            'upload-aborted',
            status=CollectionAssetUpload.Status.ABORTED,
            ended=datetime.now(UTC)
        )
        asset_upload_4 = self.create_asset_upload(
            self.asset,
            'upload-aborted-2',
            status=CollectionAssetUpload.Status.ABORTED,
            ended=datetime.now(UTC)
        )

        # Try to delete parent asset
        with self.assertRaises(ValidationError):
            self.asset.delete()
        self.assertEqual(4, len(list(CollectionAssetUpload.objects.all())))
        self.assertTrue(
            CollectionAsset.objects.all().filter(
                name=self.asset.name, collection__name=self.collection.name
            ).exists()
        )

        self.update_asset_upload(
            asset_upload_1, status=CollectionAssetUpload.Status.ABORTED, ended=datetime.now(UTC)
        )

        self.asset.delete()
        self.assertEqual(0, len(list(CollectionAssetUpload.objects.all())))
        self.assertFalse(
            CollectionAsset.objects.all().filter(
                name=self.asset.name, collection__name=self.collection.name
            ).exists()
        )
