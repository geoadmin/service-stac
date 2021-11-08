# pylint: disable=too-many-lines

import logging
from uuid import uuid4

from rest_framework import serializers

from stac_api.models import AssetUpload
from stac_api.serializers import AssetUploadSerializer
from stac_api.utils import get_sha256_multihash

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

    def test_asset_upload_deserialization_invalid(self):
        serializer = AssetUploadSerializer(data={})
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(data={'checksum:multihash': ''})
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': get_sha256_multihash(b'Test'), 'number_parts': 0
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': get_sha256_multihash(b'Test'), 'number_parts': 10001
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_asset_upload_serialization_with_md5_parts(self):
        upload_id = str(uuid4())
        checksum = get_sha256_multihash(b'Test')
        asset_upload = AssetUpload(
            asset=self.asset,
            upload_id=upload_id,
            checksum_multihash=checksum,
            number_parts=2,
            md5_parts=[{
                'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
            }, {
                'part_number': 2, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
            }]
        )
        asset_upload.full_clean()
        asset_upload.save()

        serializer = AssetUploadSerializer(asset_upload)
        data = serializer.data
        self.assertEqual(data['upload_id'], upload_id)
        self.assertEqual(data['checksum:multihash'], checksum)
        self.assertEqual(data['status'], 'in-progress')
        self.assertEqual(data['number_parts'], 2)
        self.assertEqual(
            data['md5_parts'],
            [{
                'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
            }, {
                'part_number': 2, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
            }]
        )
        self.assertNotIn('urls', data)
        self.assertNotIn('started', data)
        self.assertNotIn('completed', data)
        self.assertNotIn('aborted', data)

    def test_asset_upload_deserialization_with_md5_parts(self):
        checksum = get_sha256_multihash(b'Test')
        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 2,
                "md5_parts": [{
                    'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }, {
                    'part_number': 2, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }]
            }
        )
        serializer.is_valid(raise_exception=True)
        asset_upload = serializer.save(asset=self.asset)
        self.assertEqual(asset_upload.checksum_multihash, checksum)
        self.assertEqual(
            asset_upload.md5_parts,
            [{
                'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
            }, {
                'part_number': 2, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
            }]
        )
        self.assertEqual(asset_upload.status, AssetUpload.Status.IN_PROGRESS)
        self.assertEqual(asset_upload.ended, None)

    def test_asset_upload_deserialization_with_invalid_md5_parts(self):
        checksum = get_sha256_multihash(b'Test')
        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 2,
                "md5_parts": [{
                    'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 1,
                "md5_parts": [{
                    'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 1,
                "md5_parts": {
                    'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 1,
                "md5_parts": [{
                    'part_number': 'a', 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 1,
                "md5_parts": [{
                    'part_number': 1
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 1,
                "md5_parts": [{
                    'part_number': 2, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 1,
                "md5_parts": [{
                    'part_number': 0, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 1,
                "md5_parts": [{
                    'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }, {
                    'part_number': 2, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 2,
                "md5_parts": [{
                    'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }, {
                    'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 2,
                "md5_parts": [{
                    'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }, {
                    'part_number': 3, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 2,
                "md5_parts": ['yLLiDqX2OL7mcIMTjob60A==', 'yLLiDqX2OL7mcIMTjob60A==']
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 1,
                "md5_parts": [{
                    'part_number': 1, 'md5': ''
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'checksum:multihash': checksum,
                "number_parts": 1,
                "md5_parts": [{
                    'part_number': 1, 'md5': 2
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)
