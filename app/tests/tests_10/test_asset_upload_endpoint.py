# pylint: disable=too-many-ancestors,too-many-lines
import gzip
import hashlib
import logging
from base64 import b64encode
from datetime import datetime
from urllib import parse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

from stac_api.models import Asset
from stac_api.models import AssetUpload
from stac_api.utils import fromisoformat
from stac_api.utils import get_asset_path
from stac_api.utils import get_s3_client
from stac_api.utils import get_sha256_multihash
from stac_api.utils import utc_aware

from tests.tests_10.base_test import StacBaseTestCase
from tests.tests_10.base_test import StacBaseTransactionTestCase
from tests.tests_10.data_factory import Factory
from tests.tests_10.utils import reverse_version
from tests.utils import S3TestMixin
from tests.utils import client_login
from tests.utils import get_file_like_object
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)

KB = 1024
MB = 1024 * KB
GB = 1024 * MB


def base64_md5(data):
    return b64encode(hashlib.md5(data).digest()).decode('utf-8')


def create_md5_parts(number_parts, offset, file_like):
    return [{
        'part_number': i + 1, 'md5': base64_md5(file_like[i * offset:(i + 1) * offset])
    } for i in range(number_parts)]


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
        return reverse_version(
            'asset-detail', args=[self.collection.name, self.item.name, self.asset.name]
        )

    def get_get_multipart_uploads_path(self):
        return reverse_version(
            'asset-uploads-list', args=[self.collection.name, self.item.name, self.asset.name]
        )

    def get_create_multipart_upload_path(self):
        return reverse_version(
            'asset-uploads-list', args=[self.collection.name, self.item.name, self.asset.name]
        )

    def get_abort_multipart_upload_path(self, upload_id):
        return reverse_version(
            'asset-upload-abort',
            args=[self.collection.name, self.item.name, self.asset.name, upload_id]
        )

    def get_complete_multipart_upload_path(self, upload_id):
        return reverse_version(
            'asset-upload-complete',
            args=[self.collection.name, self.item.name, self.asset.name, upload_id]
        )

    def get_list_parts_path(self, upload_id):
        return reverse_version(
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
        file_like, checksum_multihash = get_file_like_object(1 * KB)
        offset = 1 * KB // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'checksum:multihash': checksum_multihash,
                'md5_parts': md5_parts
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
        file_like, checksum_multihash = get_file_like_object(1 * KB)
        offset = 1 * KB // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'checksum:multihash': checksum_multihash,
                'md5_parts': md5_parts
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_created_response(json_data)
        self.check_urls_response(json_data['urls'], number_parts)
        initial_upload_id = json_data['upload_id']

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'checksum:multihash': checksum_multihash,
                'md5_parts': md5_parts
            },
            content_type="application/json"
        )
        self.assertStatusCode(409, response)
        self.assertEqual(response.json()['description'], "Upload already in progress")
        self.assertIn(
            "upload_id",
            response.json(),
            msg="The upload id of the current upload is missing from response"
        )
        self.assertEqual(
            initial_upload_id,
            response.json()['upload_id'],
            msg="Current upload ID not matching the one from the 409 Conflict response"
        )

        self.assertEqual(
            self.get_asset_upload_queryset().filter(status=AssetUpload.Status.IN_PROGRESS).count(),
            1,
            msg='More than one upload in progress'
        )

        # check that there is only one multipart upload on S3
        s3 = get_s3_client()
        response = s3.list_multipart_uploads(Bucket=settings.AWS_STORAGE_BUCKET_NAME, KeyMarker=key)
        self.assertIn('Uploads', response, msg='Failed to retrieve the upload list from s3')
        self.assertEqual(len(response['Uploads']), 1, msg='More or less uploads found on S3')


class AssetUploadCreateRaceConditionTest(StacBaseTransactionTestCase, S3TestMixin):

    @mock_s3_asset_file
    def setUp(self):
        self.username = 'user'
        self.password = 'dummy-password'
        get_user_model().objects.create_superuser(self.username, password=self.password)
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.asset = self.factory.create_asset_sample(item=self.item, sample='asset-no-file').model

    def test_asset_upload_create_race_condition(self):
        workers = 5

        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 2
        file_like, checksum_multihash = get_file_like_object(1 * KB)
        offset = 1 * KB // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)
        path = reverse_version(
            'asset-uploads-list', args=[self.collection.name, self.item.name, self.asset.name]
        )

        def asset_upload_atomic_create_test(worker):
            # This method run on separate thread therefore it requires to create a new client and
            # to login it for each call.
            client = Client()
            client.login(username=self.username, password=self.password)
            return client.post(
                path,
                data={
                    'number_parts': number_parts,
                    'checksum:multihash': checksum_multihash,
                    'md5_parts': md5_parts
                },
                content_type="application/json"
            )

        # We call the POST asset upload several times in parallel with the same data to make sure
        # that we don't have any race condition.
        results, errors = self.run_parallel(workers, asset_upload_atomic_create_test)

        for _, response in results:
            self.assertStatusCode([201, 409], response)

        ok_201 = [r for _, r in results if r.status_code == 201]
        bad_409 = [r for _, r in results if r.status_code == 409]
        self.assertEqual(len(ok_201), 1, msg="More than 1 parallel request was successful")
        for response in bad_409:
            self.assertEqual(response.json()['description'], "Upload already in progress")


class AssetUpload1PartEndpointTestCase(AssetUploadBaseTest):

    def upload_asset_with_dyn_cache(self, update_interval=None):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 1
        size = 1 * KB
        file_like, checksum_multihash = get_file_like_object(size)
        md5_parts = [{'part_number': 1, 'md5': base64_md5(file_like)}]
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'md5_parts': md5_parts,
                'checksum:multihash': checksum_multihash,
                'update_interval': update_interval
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_created_response(json_data)
        self.check_urls_response(json_data['urls'], number_parts)
        self.assertIn('md5_parts', json_data)
        self.assertEqual(json_data['md5_parts'], md5_parts)

        parts = self.s3_upload_parts(json_data['upload_id'], file_like, size, number_parts)
        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': parts},
            content_type="application/json"
        )
        self.assertStatusCode(200, response)
        self.check_completed_response(response.json())
        return key

    def test_asset_upload_1_part_md5_integrity(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 1
        size = 1 * KB
        file_like, checksum_multihash = get_file_like_object(size)
        md5_parts = [{'part_number': 1, 'md5': base64_md5(file_like)}]
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'md5_parts': md5_parts,
                'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_created_response(json_data)
        self.check_urls_response(json_data['urls'], number_parts)
        self.assertIn('md5_parts', json_data)
        self.assertEqual(json_data['md5_parts'], md5_parts)

        parts = self.s3_upload_parts(json_data['upload_id'], file_like, size, number_parts)
        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': parts},
            content_type="application/json"
        )
        self.assertStatusCode(200, response)
        self.check_completed_response(response.json())
        self.assertS3ObjectExists(key)
        obj = self.get_s3_object(key)
        self.assertS3ObjectCacheControl(obj, key, max_age=7200)
        self.assertS3ObjectContentEncoding(obj, key, None)

    def test_asset_upload_dyn_cache(self):
        key = self.upload_asset_with_dyn_cache(update_interval=600)
        self.assertS3ObjectExists(key)
        obj = self.get_s3_object(key)
        self.assertS3ObjectCacheControl(obj, key, max_age=8)

    def test_asset_upload_no_cache(self):
        key = self.upload_asset_with_dyn_cache(update_interval=5)
        self.assertS3ObjectExists(key)
        obj = self.get_s3_object(key)
        self.assertS3ObjectCacheControl(obj, key, no_cache=True)

    def test_asset_upload_no_content_encoding(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 1
        size = 1 * KB
        file_like, checksum_multihash = get_file_like_object(size)
        md5_parts = [{'part_number': 1, 'md5': base64_md5(file_like)}]
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'md5_parts': md5_parts,
                'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_created_response(json_data)
        self.check_urls_response(json_data['urls'], number_parts)
        self.assertIn('md5_parts', json_data)
        self.assertEqual(json_data['md5_parts'], md5_parts)

        parts = self.s3_upload_parts(json_data['upload_id'], file_like, size, number_parts)
        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': parts},
            content_type="application/json"
        )
        self.assertStatusCode(200, response)
        self.check_completed_response(response.json())
        self.assertS3ObjectExists(key)
        obj = self.get_s3_object(key)
        self.assertS3ObjectContentEncoding(obj, key, None)

    def test_asset_upload_gzip(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 1
        size = 1 * MB
        file_like, checksum_multihash = get_file_like_object(size)
        file_like_compress = gzip.compress(file_like)
        size_compress = len(file_like_compress)
        md5_parts = [{'part_number': 1, 'md5': base64_md5(file_like_compress)}]
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'md5_parts': md5_parts,
                'checksum:multihash': checksum_multihash,
                'content_encoding': 'gzip'
            },
            content_type="application/json"
        )
        self.assertStatusCode(201, response)
        json_data = response.json()
        self.check_created_response(json_data)
        self.check_urls_response(json_data['urls'], number_parts)
        self.assertIn('md5_parts', json_data)
        self.assertEqual(json_data['md5_parts'], md5_parts)

        parts = self.s3_upload_parts(
            json_data['upload_id'], file_like_compress, size_compress, number_parts
        )
        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': parts},
            content_type="application/json"
        )
        self.assertStatusCode(200, response)
        self.check_completed_response(response.json())
        self.assertS3ObjectExists(key)
        obj = self.get_s3_object(key)
        self.assertS3ObjectContentEncoding(obj, key, encoding='gzip')


class AssetUpload2PartEndpointTestCase(AssetUploadBaseTest):

    def test_asset_upload_2_parts_md5_integrity(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 2
        size = 10 * MB  # Minimum upload part on S3 is 5 MB
        file_like, checksum_multihash = get_file_like_object(size)

        offset = size // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'md5_parts': md5_parts,
                'checksum:multihash': checksum_multihash
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

    def test_asset_upload_invalid_content_encoding(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 2
        size = 10 * MB  # Minimum upload part on S3 is 5 MB
        file_like, checksum_multihash = get_file_like_object(size)
        offset = size // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'md5_parts': md5_parts,
                'checksum:multihash': checksum_multihash,
                'content_encoding': 'hello world'
            },
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            {'content_encoding': ['Invalid encoding "hello world": must be one of '
                                  '"br, gzip"']}
        )

    def test_asset_upload_1_part_no_md5(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 1
        size = 1 * KB
        file_like, checksum_multihash = get_file_like_object(size)
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(response.json()['description'], {'md5_parts': ['This field is required.']})

    def test_asset_upload_2_parts_no_md5(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 2
        size = 10 * MB  # Minimum upload part on S3 is 5 MB
        file_like, checksum_multihash = get_file_like_object(size)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts, 'checksum:multihash': checksum_multihash
            },
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(response.json()['description'], {'md5_parts': ['This field is required.']})

    def test_asset_upload_create_empty_payload(self):
        response = self.client.post(
            self.get_create_multipart_upload_path(), data={}, content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            {
                'checksum:multihash': ['This field is required.'],
                'number_parts': ['This field is required.'],
                'md5_parts': ['This field is required.']
            }
        )

    def test_asset_upload_create_invalid_data(self):

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': 0,
                "checksum:multihash": 'abcdef',
                "md5_parts": [{
                    "part_number": '0', "md5": 'abcdef'
                }]
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

    def test_asset_upload_create_too_many_parts(self):

        number_parts = 101
        md5_parts = [{'part_number': i + 1, 'md5': 'abcdef'} for i in range(number_parts)]

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': 101, "checksum:multihash": 'abcdef', 'md5_parts': md5_parts
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

    def test_asset_upload_create_empty_md5_parts(self):

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': 2,
                "md5_parts": [],
                "checksum:multihash":
                    '12200ADEC47F803A8CF1055ED36750B3BA573C79A3AF7DA6D6F5A2AED03EA16AF3BC'
            },
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            {
                'non_field_errors': [
                    'Missing, too many or duplicate part_number in md5_parts field list: '
                    'list should have 2 item(s).'
                ]
            }
        )

    def test_asset_upload_create_duplicate_md5_parts(self):

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': 3,
                "md5_parts": [{
                    'part_number': 1, 'md5': 'asdf'
                }, {
                    'part_number': 1, 'md5': 'asdf'
                }, {
                    'part_number': 2, 'md5': 'asdf'
                }],
                "checksum:multihash":
                    '12200ADEC47F803A8CF1055ED36750B3BA573C79A3AF7DA6D6F5A2AED03EA16AF3BC'
            },
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            {
                'non_field_errors': [
                    'Missing, too many or duplicate part_number in md5_parts field list: '
                    'list should have 3 item(s).'
                ]
            }
        )

    def test_asset_upload_create_too_many_md5_parts(self):

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': 2,
                "md5_parts": [{
                    'part_number': 1, 'md5': 'asdf'
                }, {
                    'part_number': 2, 'md5': 'asdf'
                }, {
                    'part_number': 3, 'md5': 'asdf'
                }],
                "checksum:multihash":
                    '12200ADEC47F803A8CF1055ED36750B3BA573C79A3AF7DA6D6F5A2AED03EA16AF3BC'
            },
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            {
                'non_field_errors': [
                    'Missing, too many or duplicate part_number in md5_parts field list: '
                    'list should have 2 item(s).'
                ]
            }
        )

    def test_asset_upload_create_md5_parts_missing_part_number(self):

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': 2,
                "md5_parts": [
                    {
                        'part_number': 1, 'md5': 'asdf'
                    },
                    {
                        'md5': 'asdf'
                    },
                ],
                "checksum:multihash":
                    '12200ADEC47F803A8CF1055ED36750B3BA573C79A3AF7DA6D6F5A2AED03EA16AF3BC'
            },
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'],
            {'non_field_errors': ['Invalid md5_parts[1] value: part_number field missing']}
        )

    def test_asset_upload_2_parts_too_small(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 2
        size = 1 * KB  # Minimum upload part on S3 is 5 MB
        file_like, checksum_multihash = get_file_like_object(size)
        offset = size // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'checksum:multihash': checksum_multihash,
                'md5_parts': md5_parts
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
        file_like, checksum_multihash = get_file_like_object(size)
        offset = size // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'checksum:multihash': checksum_multihash,
                'md5_parts': md5_parts
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
        file_like, checksum_multihash = get_file_like_object(size)
        offset = size // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'checksum:multihash': checksum_multihash,
                'md5_parts': md5_parts
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
        file_like, checksum_multihash = get_file_like_object(size)
        offset = size // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'checksum:multihash': checksum_multihash,
                'md5_parts': md5_parts
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
        file_like, checksum_multihash = get_file_like_object(size)
        offset = size // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'checksum:multihash': checksum_multihash,
                'md5_parts': md5_parts
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

    def test_asset_upload_1_parts_duplicate_complete(self):
        key = get_asset_path(self.item, self.asset.name)
        self.assertS3ObjectNotExists(key)
        number_parts = 1
        size = 1 * KB
        file_like, checksum_multihash = get_file_like_object(size)
        offset = size // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'checksum:multihash': checksum_multihash,
                'md5_parts': md5_parts
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
        self.assertStatusCode(200, response)

        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': parts},
            content_type="application/json"
        )
        self.assertStatusCode(409, response)
        self.assertEqual(response.json()['code'], 409)
        self.assertEqual(response.json()['description'], 'No upload in progress')


class AssetUploadDeleteInProgressEndpointTestCase(AssetUploadBaseTest):

    def test_delete_asset_upload_in_progress(self):
        number_parts = 2
        size = 10 * MB  # Minimum upload part on S3 is 5 MB
        file_like, checksum_multihash = get_file_like_object(size)
        offset = size // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)

        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'checksum:multihash': checksum_multihash,
                'md5_parts': md5_parts
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

    def create_dummies_uploads(self):
        # Create some asset uploads
        for i in range(1, 4):
            AssetUpload.objects.create(
                asset=self.asset,
                upload_id=f'upload-{i}',
                status=AssetUpload.Status.ABORTED,
                checksum_multihash=get_sha256_multihash(b'upload-%d' % i),
                number_parts=2,
                ended=utc_aware(datetime.utcnow()),
                md5_parts=[]
            )
        for i in range(4, 8):
            AssetUpload.objects.create(
                asset=self.asset,
                upload_id=f'upload-{i}',
                status=AssetUpload.Status.COMPLETED,
                checksum_multihash=get_sha256_multihash(b'upload-%d' % i),
                number_parts=2,
                ended=utc_aware(datetime.utcnow()),
                md5_parts=[]
            )
        AssetUpload.objects.create(
            asset=self.asset,
            upload_id='upload-8',
            status=AssetUpload.Status.IN_PROGRESS,
            checksum_multihash=get_sha256_multihash(b'upload-8'),
            number_parts=2,
            md5_parts=[]
        )
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_get_asset_uploads(self):
        self.create_dummies_uploads()
        response = self.client.get(self.get_get_multipart_uploads_path())
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertIn('links', json_data)
        self.assertEqual(json_data['links'], [])
        self.assertIn('uploads', json_data)
        self.assertEqual(len(json_data['uploads']), self.get_asset_upload_queryset().count())
        self.assertEqual(
            [
                'upload_id',
                'status',
                'created',
                'aborted',
                'number_parts',
                'update_interval',
                'content_encoding',
                'checksum:multihash'
            ],
            list(json_data['uploads'][0].keys()),
        )
        self.assertEqual(
            [
                'upload_id',
                'status',
                'created',
                'completed',
                'number_parts',
                'update_interval',
                'content_encoding',
                'checksum:multihash'
            ],
            list(json_data['uploads'][4].keys()),
        )
        self.assertEqual(
            [
                'upload_id',
                'status',
                'created',
                'number_parts',
                'update_interval',
                'content_encoding',
                'checksum:multihash'
            ],
            list(json_data['uploads'][7].keys()),
        )

    def test_get_asset_uploads_with_content_encoding(self):
        AssetUpload.objects.create(
            asset=self.asset,
            upload_id='upload-content-encoding',
            status=AssetUpload.Status.COMPLETED,
            checksum_multihash=get_sha256_multihash(b'upload-content-encoding'),
            number_parts=2,
            ended=utc_aware(datetime.utcnow()),
            md5_parts=[],
            content_encoding='gzip'
        )
        response = self.client.get(self.get_get_multipart_uploads_path())
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertIn('links', json_data)
        self.assertEqual(json_data['links'], [])
        self.assertIn('uploads', json_data)
        self.assertEqual(len(json_data['uploads']), self.get_asset_upload_queryset().count())
        self.assertEqual(
            [
                'upload_id',
                'status',
                'created',
                'completed',
                'number_parts',
                'update_interval',
                'content_encoding',
                'checksum:multihash'
            ],
            list(json_data['uploads'][0].keys()),
        )
        self.assertEqual('gzip', json_data['uploads'][0]['content_encoding'])

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
        file_like, checksum_multihash = get_file_like_object(size)
        offset = size // number_parts
        md5_parts = create_md5_parts(number_parts, offset, file_like)
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': number_parts,
                'checksum:multihash': checksum_multihash,
                'md5_parts': md5_parts
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
