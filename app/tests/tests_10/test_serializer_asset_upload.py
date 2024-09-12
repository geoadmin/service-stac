# pylint: disable=too-many-lines

import logging
from uuid import uuid4

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from stac_api.models import AssetUpload
from stac_api.serializers.upload import AssetUploadSerializer
from stac_api.utils import get_sha256_multihash

from tests.tests_10.base_test import StacBaseTestCase
from tests.tests_10.data_factory import Factory
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
        with self.assertRaises(serializers.ValidationError, msg='no data'):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(data={'file:checksum': ''})
        with self.assertRaises(serializers.ValidationError, msg='file:checksum=""'):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'file:checksum': get_sha256_multihash(b'Test'), 'number_parts': 0
            }
        )
        with self.assertRaises(serializers.ValidationError, msg='number_parts=0'):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'file:checksum': get_sha256_multihash(b'Test'), 'number_parts': 10001
            }
        )
        with self.assertRaises(serializers.ValidationError, msg='number_parts=10001'):
            serializer.is_valid(raise_exception=True)

        for value in ['', 12, 'gzipp', 'gzip,gzip', 'hello', 'gzip, hello']:
            serializer = AssetUploadSerializer(
                data={
                    'file:checksum': get_sha256_multihash(b'Test'),
                    'number_parts': 1,
                    'md5_parts': [{
                        'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
                    }],
                    'content_encoding': value
                }
            )
            with self.assertRaises(
                serializers.ValidationError,
                msg=f'Invalid content_encoding={value} did not raised an exception'
            ):
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
        self.assertEqual(data['file:checksum'], checksum)
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
                'file:checksum': checksum,
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
                'file:checksum': checksum,
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
                'file:checksum': checksum,
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
                'file:checksum': checksum,
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
                'file:checksum': checksum,
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
                'file:checksum': checksum, "number_parts": 1, "md5_parts": [{
                    'part_number': 1
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'file:checksum': checksum,
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
                'file:checksum': checksum,
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
                'file:checksum': checksum,
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
                'file:checksum': checksum,
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
                'file:checksum': checksum,
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
                'file:checksum': checksum,
                "number_parts": 2,
                "md5_parts": ['yLLiDqX2OL7mcIMTjob60A==', 'yLLiDqX2OL7mcIMTjob60A==']
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = AssetUploadSerializer(
            data={
                'file:checksum': checksum,
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
                'file:checksum': checksum,
                "number_parts": 1,
                "md5_parts": [{
                    'part_number': 1, 'md5': 2
                }]
            }
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class TestAssetUploadSerializationContentEncoding(StacBaseTestCase):

    @classmethod
    @mock_s3_asset_file
    def setUpTestData(cls):
        cls.data_factory = Factory()
        cls.collection = cls.data_factory.create_collection_sample().model
        cls.item = cls.data_factory.create_item_sample(collection=cls.collection).model
        cls.asset = cls.data_factory.create_asset_sample(item=cls.item).model

    def get_asset_upload_default(self):
        upload_id = str(uuid4())
        checksum = get_sha256_multihash(b'Test')
        return {
            'asset': self.asset,
            'upload_id': upload_id,
            'checksum_multihash': checksum,
            'number_parts': 1,
            'md5_parts': [{
                'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
            }]
        }

    def create_asset_upload(self, **kwargs):
        asset_upload = AssetUpload(**kwargs)
        asset_upload.full_clean()
        asset_upload.save()
        return asset_upload

    def test_asset_upload_serialization_default_content_encoding(self):
        data = self.get_asset_upload_default()
        asset_upload = self.create_asset_upload(**data)

        serializer = AssetUploadSerializer(asset_upload)
        data = serializer.data
        self.assertIn('content_encoding', data)
        self.assertEqual(data['content_encoding'], '')

    def test_asset_upload_serialization_empty_content_encoding(self):
        data = self.get_asset_upload_default()
        asset_upload = self.create_asset_upload(**data, content_encoding='')

        serializer = AssetUploadSerializer(asset_upload)
        data = serializer.data
        self.assertIn('content_encoding', data)
        self.assertEqual(data['content_encoding'], '')

    def test_asset_upload_serialization_valid_content_encoding(self):
        data = self.get_asset_upload_default()
        asset_upload = self.create_asset_upload(content_encoding='br', **data)

        serializer = AssetUploadSerializer(asset_upload)
        data = serializer.data
        self.assertIn('content_encoding', data)
        self.assertEqual(data['content_encoding'], 'br')


class TestAssetUploadDeserializationContentEncoding(StacBaseTestCase):

    @classmethod
    @mock_s3_asset_file
    def setUpTestData(cls):
        cls.data_factory = Factory()
        cls.collection = cls.data_factory.create_collection_sample().model
        cls.item = cls.data_factory.create_item_sample(collection=cls.collection).model
        cls.asset = cls.data_factory.create_asset_sample(item=cls.item).model

    def get_asset_upload_default(self):
        return {
            'file:checksum': get_sha256_multihash(b'Test'),
            "number_parts": 1,
            "md5_parts": [{
                'part_number': 1, 'md5': 'yLLiDqX2OL7mcIMTjob60A=='
            }]
        }

    def deserialize_asset_upload(self, data):
        serializer = AssetUploadSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        asset_upload = serializer.save(asset=self.asset)
        return asset_upload

    def test_asset_upload_deserialization_without_content_encoding(self):
        data = self.get_asset_upload_default()
        asset_upload = self.deserialize_asset_upload(data)
        self.assertEqual(asset_upload.content_encoding, '')

    def test_asset_upload_deserialization_with_empty_content_encoding(self):
        data = self.get_asset_upload_default()
        data['content_encoding'] = ''
        try:
            asset_upload = self.deserialize_asset_upload(data)
        except ValidationError as err:
            self.assertIn('content_encoding', err.detail)
        else:
            self.fail('Empty content encoding did not raised an exception')

    def test_asset_upload_deserialization_with_valid_content_encoding(self):
        data = self.get_asset_upload_default()
        data['content_encoding'] = 'gzip'
        asset_upload = self.deserialize_asset_upload(data)
        self.assertEqual(asset_upload.content_encoding, 'gzip')

    def test_asset_upload_deserialization_with_invalid_content_encoding(self):
        data = self.get_asset_upload_default()
        data['content_encoding'] = 'hello'
        try:
            asset_upload = self.deserialize_asset_upload(data)
        except ValidationError as err:
            self.assertIn('content_encoding', err.detail)
        else:
            self.fail('Invalid content encoding did not raised an exception')
