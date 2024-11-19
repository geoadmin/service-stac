from unittest.mock import patch

import environ
from parameterized import parameterized

from django.conf import settings
from django.test import TestCase

from stac_api.s3_multipart_upload import MultipartUpload
from stac_api.utils import AVAILABLE_S3_BUCKETS
from stac_api.utils import get_asset_path
from stac_api.utils import select_s3_bucket

from tests.tests_10.data_factory import Factory
from tests.utils import get_file_like_object
from tests.utils import mock_s3_bucket


class MultipartUploadMultipleBucketTest(TestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.asset = self.factory.create_asset_sample(item=self.item, sample='asset-no-file').model

        mock_s3_bucket(AVAILABLE_S3_BUCKETS.legacy)
        mock_s3_bucket(AVAILABLE_S3_BUCKETS.managed)

    def test_create_multipart_upload(self):
        _, checksum_multihash = get_file_like_object(1024)
        asset_path = get_asset_path(self.asset.item, self.asset.name)

        def get_url(s3_bucket):
            executor = MultipartUpload(s3_bucket)

            upload_id = executor.create_multipart_upload(
                asset_path,
                self.asset,
                checksum_multihash,
                update_interval=1,
                content_encoding='text/html'
            )

            url = executor.create_presigned_url(
                asset_path, self.asset, 1, upload_id, "some-checksum"
            )
            return upload_id, url['url']

        # First upload goes to the legacy bucket
        upload_id, url = get_url(AVAILABLE_S3_BUCKETS.legacy)

        self.assertIn(
            f"https://legacy.s3.amazonaws.com/collection-1/item-1/asset-1.tiff?uploadId={upload_id}",
            url
        )

        # Second upload goes to the managed bucket
        upload_id, url = get_url(AVAILABLE_S3_BUCKETS.managed)

        self.assertIn(
            f"https://managed.s3.amazonaws.com/collection-1/item-1/asset-1.tiff?uploadId={upload_id}",
            url
        )

    @parameterized.expand([
        AVAILABLE_S3_BUCKETS.legacy,
        AVAILABLE_S3_BUCKETS.managed,
    ],)
    @patch("stac_api.s3_multipart_upload.MultipartUpload.call_s3_api")
    def test_complete_multipart_upload(self, s3_bucket, mock_call):
        mock_call.return_value = {"Location": "some location"}

        executor = MultipartUpload(s3_bucket)

        executor.complete_multipart_upload("foo", self.asset, [], "upload_id")

        config = settings.AWS_SETTINGS[s3_bucket.name]

        mock_call.assert_called_once_with(
            executor.s3.complete_multipart_upload,
            Bucket=config['S3_BUCKET_NAME'],
            Key="foo",
            MultipartUpload={'Parts': []},
            UploadId="upload_id",
            log_extra={
                'parts': [],
                'upload_id': 'upload_id',
                'collection': self.asset.item.collection.name,
                'item': self.asset.item.name,
                'asset': self.asset.name
            }
        )

    @parameterized.expand([
        AVAILABLE_S3_BUCKETS.legacy,
        AVAILABLE_S3_BUCKETS.managed,
    ],)
    @patch("stac_api.s3_multipart_upload.MultipartUpload.call_s3_api")
    def test_abort_multipart_upload(self, s3_bucket, mock_call):
        executor = MultipartUpload(s3_bucket)

        executor.abort_multipart_upload("foo", self.asset, "upload_id")

        config = settings.AWS_SETTINGS[s3_bucket.name]

        mock_call.assert_called_once_with(
            executor.s3.abort_multipart_upload,
            Bucket=config['S3_BUCKET_NAME'],
            Key="foo",
            UploadId="upload_id",
            log_extra={
                'upload_id': 'upload_id', 'asset': self.asset.name
            }
        )

    @parameterized.expand([
        AVAILABLE_S3_BUCKETS.legacy,
        AVAILABLE_S3_BUCKETS.managed,
    ],)
    @patch("stac_api.s3_multipart_upload.MultipartUpload.call_s3_api")
    def test_list_upload_parts(self, s3_bucket, mock_call):
        executor = MultipartUpload(s3_bucket)

        executor.list_upload_parts("foo", self.asset, "upload_id", 3, 2)

        config = settings.AWS_SETTINGS[s3_bucket.name]

        mock_call.assert_called_once_with(
            executor.s3.list_parts,
            Bucket=config['S3_BUCKET_NAME'],
            Key="foo",
            UploadId="upload_id",
            MaxParts=3,
            PartNumberMarker=2,
            log_extra={
                'collection': self.asset.item.collection.name,
                'item': self.asset.item.name,
                'asset': self.asset.name,
                'upload_id': 'upload_id',
            }
        )


class TestBucketSelector(TestCase):

    @parameterized.expand([
        ('ch.meteoschweiz.ogd-rainfall', AVAILABLE_S3_BUCKETS.managed),
        ('ch.meteoschweiz.ogd-downpour', AVAILABLE_S3_BUCKETS.managed),
        ('ch.meteoschweiz.precipitation', AVAILABLE_S3_BUCKETS.legacy),
        ('ch.swisstopo.bgdi', AVAILABLE_S3_BUCKETS.managed),
        ('ch.bafu.slipouts', AVAILABLE_S3_BUCKETS.legacy),
        ('ch.are.hauptstrassennetz', AVAILABLE_S3_BUCKETS.managed),
        ('ch.are.gemeindetypen', AVAILABLE_S3_BUCKETS.managed),
        ('ch.are.landschaftstypen', AVAILABLE_S3_BUCKETS.managed),
    ])
    def test_bucket_selection(self, collection_name, expected_bucket):
        """Test if the pattern selection works"""
        patterns = [r'ch\.meteoschweiz\.ogd-.*', r'ch\.swisstopo\.bgdi.*', r'ch\.are\..*']
        with self.settings(MANAGED_BUCKET_COLLECTION_PATTERNS=patterns):
            bucket_name = select_s3_bucket(collection_name)

        self.assertEqual(bucket_name, expected_bucket)

    @parameterized.expand([
        'ch.meteoschweiz.ogd-heatwave',
        'ch.meteoschweiz.ogd-snowstorms',
    ])
    def test_managed_bucket_patterns(self, collection_name):
        """Test if the patterns in the environment work correctly. We take the
        default environment explicitly here.
        This might appear a bit artificial, but otherwise we have no way
        to machine-test the functioning of getting the values from the env
        list, use them as regex, and match the collection name.
        """
        env = environ.Env()
        env.read_env("../.local.default")

        patterns = env.list('MANAGED_BUCKET_COLLECTION_PATTERNS')
        with self.settings(MANAGED_BUCKET_COLLECTION_PATTERNS=patterns):
            bucket_name = select_s3_bucket(collection_name)

        self.assertEqual(bucket_name, AVAILABLE_S3_BUCKETS.managed)
