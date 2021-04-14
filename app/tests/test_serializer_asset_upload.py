# pylint: disable=too-many-lines

import logging
from datetime import datetime
from datetime import timedelta
from uuid import uuid4

from rest_framework.exceptions import ValidationError

from stac_api.models import AssetUpload
from stac_api.serializers import AssetUploadSerializer
from stac_api.utils import get_sha256_multihash
from stac_api.utils import isoformat
from stac_api.utils import utc_aware

from tests.base_test import StacBaseTestCase
from tests.data_factory import Factory
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)


class AssetUploadSerializationTestCase(StacBaseTestCase):

    @classmethod
    @mock_s3_asset_file
    def setUpTestData(cls):
        cls.data_factory = Factory()
        cls.collection = cls.data_factory.create_collection_sample().model
        cls.item = cls.data_factory.create_item_sample(collection=cls.collection).model
        cls.asset = cls.data_factory.create_asset_sample(item=cls.item).model

    def setUp(self):  # pylint: disable=invalid-name
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_upload_serialization(self):
        upload_id = str(uuid4())
        checksum = get_sha256_multihash(b'Test')
        asset_upload = AssetUpload(
            asset=self.asset, upload_id=upload_id, checksum_multihash=checksum, number_parts=1
        )
        asset_upload.full_clean()
        asset_upload.save()

        serializer = AssetUploadSerializer(asset_upload)
        data = serializer.data
        self.assertEqual(data['upload_id'], upload_id)
        self.assertEqual(data['checksum:multihash'], checksum)
        self.assertEqual(data['status'], 'in-progress')
        self.assertEqual(data['number_parts'], 1)
        self.assertNotIn('urls', data)
        self.assertNotIn('started', data)
        self.assertNotIn('completed', data)
        self.assertNotIn('aborted', data)

        urls = [['http://example.com', 3600]]
        started = utc_aware(datetime.utcnow())
        ended = utc_aware(datetime.utcnow() + timedelta(seconds=5))
        asset_upload.started = started
        asset_upload.number_parts = 1
        asset_upload.urls = urls
        asset_upload.ended = ended
        asset_upload.status = AssetUpload.Status.COMPLETED
        asset_upload.full_clean()
        asset_upload.save()

        serializer = AssetUploadSerializer(asset_upload)
        data = serializer.data
        self.assertEqual(data['status'], 'completed')
        self.assertEqual(data['urls'], urls)
        self.assertEqual(data['completed'], isoformat(ended))
        self.assertNotIn('aborted', data)
        self.assertEqual(data['number_parts'], 1)

        asset_upload.status = AssetUpload.Status.ABORTED
        asset_upload.full_clean()
        asset_upload.save()
        serializer = AssetUploadSerializer(asset_upload)
        data = serializer.data
        self.assertEqual(data['status'], 'aborted')
        self.assertEqual(data['aborted'], isoformat(ended))

    def test_asset_upload_deserialization(self):
        checksum = get_sha256_multihash(b'Test')
        serializer = AssetUploadSerializer(data={'checksum:multihash': checksum, "number_parts": 1})
        serializer.is_valid(raise_exception=True)
        asset_upload = serializer.save(asset=self.asset)
        self.assertEqual(asset_upload.checksum_multihash, checksum)
        self.assertEqual(asset_upload.status, AssetUpload.Status.IN_PROGRESS)
        self.assertEqual(asset_upload.ended, None)

        ended = utc_aware(datetime.utcnow())
        serializer = AssetUploadSerializer(
            instance=asset_upload,
            data={
                'status': 'completed',
                'checksum:multihash': asset_upload.checksum_multihash,
                'ended': isoformat(ended),
                "number_parts": 1
            }
        )
        serializer.is_valid(raise_exception=True)
        asset_upload = serializer.save(asset=asset_upload.asset)
        self.assertEqual(asset_upload.ended, ended)
        self.assertEqual(asset_upload.status, AssetUpload.Status.COMPLETED)

    def test_asset_upload_deserialization_invalid(self):
        serializer = AssetUploadSerializer(data={})
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(data={'checksum:multihash': ''})
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': get_sha256_multihash(b'Test'), 'number_parts': 0
            }
        )
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': get_sha256_multihash(b'Test'), 'number_parts': 10001
            }
        )
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)
