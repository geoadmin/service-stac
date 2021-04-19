# pylint: disable=too-many-ancestors
import logging
import os
from datetime import datetime
from urllib import parse

from django.conf import settings
from django.test import Client
from django.urls import reverse

from stac_api.models import Asset
from stac_api.models import AssetUpload
from stac_api.utils import fromisoformat
from stac_api.utils import get_asset_path
from stac_api.utils import get_s3_client
from stac_api.utils import get_sha256_multihash
from stac_api.utils import utc_aware

from tests.base_test import StacBaseTestCase
from tests.data_factory import Factory
from tests.utils import S3TestMixin
from tests.utils import client_login
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)

KB = 1024
MB = 1024 * KB
GB = 1024 * MB


class AssetUploadBaseTest(StacBaseTestCase, S3TestMixin):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        client_login(self.client)
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.asset = self.factory.create_asset_sample(item=self.item, sample='asset-no-file').model
        self.maxDiff = None  # pylint: disable=invalid-name

    def get_asset_upload_queryset(self):
        return AssetUpload.objects.all().filter(
            asset__item__collection__name=self.collection.name,
            asset__item__name=self.item.name,
            asset__name=self.asset.name,
        )

    def get_delete_asset_path(self):
        return reverse('asset-detail', args=[self.collection.name, self.item.name, self.asset.name])

    def get_get_multipart_uploads_path(self):
        return reverse(
            'asset-uploads-list', args=[self.collection.name, self.item.name, self.asset.name]
        )

    def get_create_multipart_upload_path(self):
        return reverse(
            'asset-uploads-list', args=[self.collection.name, self.item.name, self.asset.name]
        )

    def get_abort_multipart_upload_path(self, upload_id):
        return reverse(
            'asset-upload-abort',
            args=[self.collection.name, self.item.name, self.asset.name, upload_id]
        )

    def get_complete_multipart_upload_path(self, upload_id):
        return reverse(
            'asset-upload-complete',
            args=[self.collection.name, self.item.name, self.asset.name, upload_id]
        )

    def get_list_parts_path(self, upload_id):
        return reverse(
            'asset-upload-parts-list',
            args=[self.collection.name, self.item.name, self.asset.name, upload_id]
        )

    def s3_upload_parts(self, upload_id, file_like, size, number_parts):
        s3 = get_s3_client()
        key = get_asset_path(self.item, self.asset.name)
        parts = []
        # split the file into parts
        start = 0
        offset = size // number_parts
        for part in range(1, number_parts + 1):
            # use the s3 client to upload the file instead of the presigned url due to the s3
            # mocking
            response = s3.upload_part(
                Body=file_like[start:start + offset],
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=key,
                PartNumber=part,
                UploadId=upload_id
            )
            start += offset
            parts.append({'etag': response['ETag'], 'part_number': part})
        return parts

    def get_file_like_object(self, size):
        file_like = os.urandom(size)
        checksum_multihash = get_sha256_multihash(file_like)
        return file_like, checksum_multihash

    def check_urls_response(self, urls, number_parts):
        now = utc_aware(datetime.utcnow())
        self.assertEqual(len(urls), number_parts)
        for i, url in enumerate(urls):
            self.assertListEqual(
                list(url.keys()), ['url', 'part', 'expires'], msg='Url dictionary keys missing'
            )
            self.assertEqual(
                url['part'], i + 1, msg=f'Part {url["part"]} does not match the url index {i}'
            )
            try:
                url_parsed = parse.urlparse(url["url"])
                self.assertIn(url_parsed[0], ['http', 'https'])
            except ValueError as error:
                self.fail(msg=f"Invalid url {url['url']} for part {url['part']}: {error}")
            try:
                expires_dt = fromisoformat(url['expires'])
                self.assertGreater(
                    expires_dt,
                    now,
                    msg=f"expires {url['expires']} for part {url['part']} is not in future"
                )
            except ValueError as error:
                self.fail(msg=f"Invalid expires {url['expires']} for part {url['part']}: {error}")

    def check_created_response(self, json_response):
        self.assertNotIn('completed', json_response)
        self.assertNotIn('aborted', json_response)
        self.assertIn('upload_id', json_response)
        self.assertIn('status', json_response)
        self.assertIn('number_parts', json_response)
        self.assertIn('checksum:multihash', json_response)
        self.assertIn('urls', json_response)
        self.assertEqual(json_response['status'], 'in-progress')

    def check_completed_response(self, json_response):
        self.assertNotIn('urls', json_response)
        self.assertNotIn('aborted', json_response)
        self.assertIn('upload_id', json_response)
        self.assertIn('status', json_response)
        self.assertIn('number_parts', json_response)
        self.assertIn('checksum:multihash', json_response)
        self.assertIn('completed', json_response)
        self.assertEqual(json_response['status'], 'completed')
        self.assertGreater(
            fromisoformat(json_response['completed']), fromisoformat(json_response['created'])
        )

    def check_aborted_response(self, json_response):
        self.assertNotIn('urls', json_response)
        self.assertNotIn('completed', json_response)
        self.assertIn('upload_id', json_response)
        self.assertIn('status', json_response)
        self.assertIn('number_parts', json_response)
        self.assertIn('checksum:multihash', json_response)
        self.assertIn('aborted', json_response)
        self.assertEqual(json_response['status'], 'aborted')
        self.assertGreater(
            fromisoformat(json_response['aborted']), fromisoformat(json_response['created'])
        )


class AssetUploadCreateEndpointTestCase(AssetUploadBaseTest):

    def test_asset_upload_create_abort_multipart(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 2
        file_like, checksum_multihash = self.get_file_like_object(1 * KB)
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_created_response(json_data)

        self.check_urls_response(json_data['urls'], number_parts)

        response = self.client.post(
            self.get_abort_multipart_upload_path(json_data['upload_id']),
            data={},
            content_type="application/json"
        )
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.check_aborted_response(json_data)
        self.assertFalse(
            self.get_asset_upload_queryset().filter(status=AssetUpload.Status.IN_PROGRESS).exists(),
            msg='In progress upload found'
        )
        self.assertTrue(
            self.get_asset_upload_queryset().filter(status=AssetUpload.Status.ABORTED).exists(),
            msg='Aborted upload not found'
        )
        # check that there is only one multipart upload on S3
        s3 = get_s3_client()
        response = s3.list_multipart_uploads(Bucket=settings.AWS_STORAGE_BUCKET_NAME, KeyMarker=key)
        self.assertNotIn('Uploads', response, msg='uploads found on S3')

    def test_asset_upload_create_multipart_duplicate(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 2
        file_like, checksum_multihash = self.get_file_like_object(1 * KB)
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_created_response(json_data)
        self.check_urls_response(json_data['urls'], number_parts)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)

        self.assertEqual(
            self.get_asset_upload_queryset().filter(status=AssetUpload.Status.IN_PROGRESS).count(),
            1,
            msg='More than one upload in progress'
        )
        self.assertTrue(
            self.get_asset_upload_queryset().filter(status=AssetUpload.Status.ABORTED).exists(),
            msg='Aborted upload not found'
        )
        # check that there is only one multipart upload on S3
        s3 = get_s3_client()
        response = s3.list_multipart_uploads(Bucket=settings.AWS_STORAGE_BUCKET_NAME, KeyMarker=key)
        self.assertIn('Uploads', response, msg='Failed to retrieve the upload list from s3')
        self.assertEqual(len(response['Uploads']), 1, msg='More or less uploads found on S3')


class AssetUpload1PartEndpointTestCase(AssetUploadBaseTest):

    def test_asset_upload_1_part(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 1
        size = 1 * KB
        file_like, checksum_multihash = self.get_file_like_object(size)
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_created_response(json_data)
        self.check_urls_response(json_data['urls'], number_parts)

        parts = self.s3_upload_parts(json_data['upload_id'], file_like, size, number_parts)

        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': parts},
            content_type="application/json"
        )
        self.assertStatusCode(200, response)
        self.check_completed_response(response.json())
        self.assertS3ObjectExists(key)


class AssetUpload2PartEndpointTestCase(AssetUploadBaseTest):

    def test_asset_upload_2_parts(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 2
        size = 10 * MB  # Minimum upload part on S3 is 5 MB
        file_like, checksum_multihash = self.get_file_like_object(size)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_created_response(json_data)
        self.check_urls_response(json_data['urls'], number_parts)

        parts = self.s3_upload_parts(json_data['upload_id'], file_like, size, number_parts)

        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': parts},
            content_type="application/json"
        )
        self.assertStatusCode(200, response)
        self.check_completed_response(response.json())
        self.assertS3ObjectExists(key)


class AssetUploadInvalidEndpointTestCase(AssetUploadBaseTest):

    def test_asset_upload_create_invalid(self):
        response = self.client.post(
            self.get_create_multipart_upload_path(), data={}, content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            {
                'checksum:multihash': ['This field is required.'],
                'number_parts': ['This field is required.']
            }
        )

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': 0, "checksum:multihash": 'abcdef'
            },
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            {
                'checksum:multihash': ['Invalid multihash value; Invalid varint provided'],
                'number_parts': ['Ensure this value is greater than or equal to 1.']
            }
        )

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': 101, "checksum:multihash": 'abcdef'
            },
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            {
                'checksum:multihash': ['Invalid multihash value; Invalid varint provided'],
                'number_parts': ['Ensure this value is less than or equal to 100.']
            }
        )

    def test_asset_upload_2_parts_too_small(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 2
        size = 1 * KB  # Minimum upload part on S3 is 5 MB
        file_like, checksum_multihash = self.get_file_like_object(size)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_urls_response(json_data['urls'], number_parts)

        parts = self.s3_upload_parts(json_data['upload_id'], file_like, size, number_parts)

        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': parts},
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            [
                'An error occurred (EntityTooSmall) when calling the CompleteMultipartUpload '
                'operation: Your proposed upload is smaller than the minimum allowed object size.'
            ]
        )
        self.assertS3ObjectNotExists(key)

    def test_asset_upload_1_parts_invalid_etag(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 1
        size = 1 * KB
        file_like, checksum_multihash = self.get_file_like_object(size)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_urls_response(json_data['urls'], number_parts)

        parts = self.s3_upload_parts(json_data['upload_id'], file_like, size, number_parts)

        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': [{
                'etag': 'dummy', 'part_number': 1
            }]},
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            [
                'An error occurred (InvalidPart) when calling the CompleteMultipartUpload '
                'operation: One or more of the specified parts could not be found. The part '
                'might not have been uploaded, or the specified entity tag might not have '
                "matched the part's entity tag."
            ]
        )
        self.assertS3ObjectNotExists(key)

    def test_asset_upload_1_parts_too_many_parts_in_complete(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 1
        size = 1 * KB
        file_like, checksum_multihash = self.get_file_like_object(size)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_urls_response(json_data['urls'], number_parts)

        parts = self.s3_upload_parts(json_data['upload_id'], file_like, size, number_parts)
        parts.append({'etag': 'dummy', 'number_part': 2})

        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': parts},
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(response.json()['description'], {'parts': ['Too many parts']})
        self.assertS3ObjectNotExists(key)

    def test_asset_upload_2_parts_incomplete_upload(self):
        number_parts = 2
        size = 10 * MB
        file_like, checksum_multihash = self.get_file_like_object(size)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_urls_response(json_data['urls'], number_parts)

        parts = self.s3_upload_parts(json_data['upload_id'], file_like, size // 2, 1)
        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': parts},
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(response.json()['description'], {'parts': ['Too few parts']})

    def test_asset_upload_1_parts_invalid_complete(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 1
        size = 1 * KB
        file_like, checksum_multihash = self.get_file_like_object(size)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_urls_response(json_data['urls'], number_parts)

        parts = self.s3_upload_parts(json_data['upload_id'], file_like, size, number_parts)

        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={},
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(response.json()['description'], {'parts': 'Missing required field'})

        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': []},
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(response.json()['description'], {'parts': ['This list may not be empty.']})

        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': ["dummy-etag"]},
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            {
                'parts': {
                    '0': {
                        'non_field_errors':
                            ['Invalid data. Expected a dictionary, '
                             'but got str.']
                    }
                }
            }
        )
        self.assertS3ObjectNotExists(key)


class AssetUploadDeleteInProgressEndpointTestCase(AssetUploadBaseTest):

    def test_delete_asset_upload_in_progress(self):
        number_parts = 2
        size = 10 * MB  # Minimum upload part on S3 is 5 MB
        file_like, checksum_multihash = self.get_file_like_object(size)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        upload_id = response.json()['upload_id']

        response = self.client.delete(self.get_delete_asset_path())
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'], ['Asset asset-1.tiff has still an upload in progress']
        )

        self.assertTrue(
            Asset.objects.all().filter(
                item__collection__name=self.collection.name,
                item__name=self.item.name,
                name=self.asset.name
            ).exists(),
            msg='Asset has been deleted'
        )

        response = self.client.post(self.get_abort_multipart_upload_path(upload_id))
        self.assertStatusCode(200, response)

        response = self.client.delete(self.get_delete_asset_path())
        self.assertStatusCode(200, response)

        self.assertFalse(
            Asset.objects.all().filter(
                item__collection__name=self.collection.name,
                item__name=self.item.name,
                name=self.asset.name
            ).exists(),
            msg='Asset has not been deleted'
        )


class GetAssetUploadsEndpointTestCase(AssetUploadBaseTest):

    def setUp(self):
        super().setUp()
        # Create some asset uploads
        for i in range(1, 4):
            AssetUpload.objects.create(
                asset=self.asset,
                upload_id=f'upload-{i}',
                status=AssetUpload.Status.ABORTED,
                checksum_multihash=get_sha256_multihash(b'upload-%d' % i),
                number_parts=2,
                ended=utc_aware(datetime.utcnow())
            )
        for i in range(4, 8):
            AssetUpload.objects.create(
                asset=self.asset,
                upload_id=f'upload-{i}',
                status=AssetUpload.Status.COMPLETED,
                checksum_multihash=get_sha256_multihash(b'upload-%d' % i),
                number_parts=2,
                ended=utc_aware(datetime.utcnow())
            )
        AssetUpload.objects.create(
            asset=self.asset,
            upload_id='upload-8',
            status=AssetUpload.Status.IN_PROGRESS,
            checksum_multihash=get_sha256_multihash(b'upload-8'),
            number_parts=2
        )
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_get_asset_uploads(self):
        response = self.client.get(self.get_get_multipart_uploads_path())
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertIn('links', json_data)
        self.assertEqual(json_data['links'], [])
        self.assertIn('uploads', json_data)
        self.assertEqual(len(json_data['uploads']), self.get_asset_upload_queryset().count())
        self.assertEqual(
            ['upload_id', 'status', 'created', 'aborted', 'number_parts', 'checksum:multihash'],
            list(json_data['uploads'][0].keys()),
        )
        self.assertEqual(
            ['upload_id', 'status', 'created', 'completed', 'number_parts', 'checksum:multihash'],
            list(json_data['uploads'][4].keys()),
        )
        self.assertEqual(
            ['upload_id', 'status', 'created', 'number_parts', 'checksum:multihash'],
            list(json_data['uploads'][7].keys()),
        )

    def test_get_asset_uploads_status_query(self):
        response = self.client.get(
            self.get_get_multipart_uploads_path(), {'status': AssetUpload.Status.ABORTED}
        )
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertIn('uploads', json_data)
        self.assertGreater(len(json_data), 1)
        self.assertEqual(
            len(json_data['uploads']),
            self.get_asset_upload_queryset().filter(status=AssetUpload.Status.ABORTED).count(),
        )
        for upload in json_data['uploads']:
            self.assertEqual(upload['status'], AssetUpload.Status.ABORTED)


class AssetUploadListPartsEndpointTestCase(AssetUploadBaseTest):

    def test_asset_upload_list_parts(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 4
        size = 5 * MB * number_parts
        file_like, checksum_multihash = self.get_file_like_object(size)
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        upload_id = json_data['upload_id']
        self.check_urls_response(json_data['urls'], number_parts)

        # List the uploaded parts should be empty
        response = self.client.get(self.get_list_parts_path(upload_id))
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertIn('links', json_data, msg='missing required field in list parts response')
        self.assertIn('parts', json_data, msg='missing required field in list parts response')
        self.assertEqual(len(json_data['parts']), 0, msg='parts should be empty')

        # upload all the parts
        parts = self.s3_upload_parts(upload_id, file_like, size, number_parts)

        # List the uploaded parts should have 4 parts
        response = self.client.get(self.get_list_parts_path(upload_id))
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertIn('links', json_data, msg='missing required field in list parts response')
        self.assertIn('parts', json_data, msg='missing required field in list parts response')
        self.assertEqual(len(json_data['parts']), number_parts)
        for part in json_data['parts']:
            self.assertIn('etag', part)
            self.assertIn('modified', part)
            self.assertIn('size', part)
            self.assertIn('part_number', part)

        # Unfortunately moto doesn't support yet the MaxParts
        # (see https://github.com/spulec/moto/issues/2680)
        # Test the list parts pagination
        # response = self.client.get(self.get_list_parts_path(upload_id), {'limit': 2})
        # self.assertStatusCode(200, response)
        # json_data = response.json()
        # self.assertIn('links', json_data, msg='missing required field in list parts response')
        # self.assertIn('parts', json_data, msg='missing required field in list parts response')
        # self.assertEqual(len(json_data['parts']), number_parts)
        # for part in json_data['parts']:
        #     self.assertIn('etag', part)
        #     self.assertIn('modified', part)
        #     self.assertIn('size', part)
        #     self.assertIn('part_number', part)

        # Complete the upload
        response = self.client.post(
            self.get_complete_multipart_upload_path(upload_id),
            data={'parts': parts},
            content_type="application/json"
        )
        self.assertStatusCode(200, response)
        self.assertS3ObjectExists(key)
