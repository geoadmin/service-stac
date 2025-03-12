import logging
from base64 import b64encode
from datetime import datetime
from json import dumps
from json import loads
from pprint import pformat

from django.contrib.auth import get_user_model
from django.test import Client
from django.test import override_settings
from django.urls import reverse

from rest_framework.authtoken.models import Token

from stac_api.models.collection import CollectionAsset
from stac_api.utils import get_collection_asset_path
from stac_api.utils import utc_aware

from tests.tests_10.base_test import STAC_BASE_V
from tests.tests_10.base_test import StacBaseTestCase
from tests.tests_10.base_test import StacBaseTransactionTestCase
from tests.tests_10.data_factory import Factory
from tests.tests_10.utils import reverse_version
from tests.utils import S3TestMixin
from tests.utils import disableLogger
from tests.utils import get_auth_headers
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)


def to_dict(input_ordered_dict):
    return loads(dumps(input_ordered_dict))


class CollectionAssetsEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.asset_1 = self.factory.create_collection_asset_sample(
            collection=self.collection, name="asset-1.tiff", db_create=True
        )
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_assets_endpoint(self):
        collection_name = self.collection.name
        # To test the assert ordering make sure to not create them in ascent order
        asset_2 = self.factory.create_collection_asset_sample(
            collection=self.collection, sample='asset-2', name="asset-2.txt", db_create=True
        )
        asset_3 = self.factory.create_collection_asset_sample(
            collection=self.collection, name="asset-0.pdf", sample='asset-3', db_create=True
        )
        response = self.client.get(f"/{STAC_BASE_V}/collections/{collection_name}/assets")
        self.assertStatusCode(200, response)
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        self.assertIn('assets', json_data, msg='assets is missing in response')
        self.assertEqual(
            3, len(json_data['assets']), msg='Number of assets doesn\'t match the expected'
        )

        # Check that the output is sorted by name
        asset_ids = [asset['id'] for asset in json_data['assets']]
        self.assertListEqual(asset_ids, sorted(asset_ids), msg="Assets are not sorted by ID")

        asset_samples = sorted([self.asset_1, asset_2, asset_3], key=lambda asset: asset['name'])
        for i, asset in enumerate(asset_samples):
            # self.check_stac_asset(asset.json, json_data['assets'][i], collection_name, item_name)
            self.check_stac_collection_asset(asset.json, json_data['assets'][i], collection_name)

    def test_assets_endpoint_collection_does_not_exist(self):
        collection_name = "non-existent"
        response = self.client.get(f"/{STAC_BASE_V}/collections/{collection_name}/assets")
        self.assertStatusCode(404, response)

    def test_single_asset_endpoint(self):
        collection_name = self.collection.name
        asset_name = self.asset_1["name"]
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        self.check_stac_collection_asset(self.asset_1.json, json_data, collection_name)

        # The ETag change between each test call due to the created, updated time that are in the
        # hash computation of the ETag
        self.assertEtagHeader(None, response)


@override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
class CollectionAssetsUnimplementedEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.client = Client(headers=get_auth_headers())
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_unimplemented_post(self):
        collection_name = self.collection.name
        asset = self.factory.create_collection_asset_sample(
            collection=self.collection, required_only=True
        )
        response = self.client.post(
            f'/{STAC_BASE_V}/collections/{collection_name}/assets',
            data=asset.get_json('post'),
            content_type="application/json"
        )
        self.assertStatusCode(405, response)


@override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
class CollectionAssetsCreateEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.client = Client(headers=get_auth_headers())
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_upsert_create_only_required(self):
        collection_name = self.collection.name
        asset = self.factory.create_collection_asset_sample(
            collection=self.collection, required_only=True
        )
        path = \
            f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset["name"]}'
        json_to_send = asset.get_json('put')
        # Send a non normalized form of the type to see if it is also accepted
        json_to_send['type'] = 'image/TIFF;application=geotiff; Profile=cloud-optimized'
        response = self.client.put(path, data=json_to_send, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.assertLocationHeader(f"{path}", response)
        self.check_stac_collection_asset(asset.json, json_data, collection_name)

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_collection_asset(asset.json, json_data, collection_name)

        # make sure that the optional fields are not present
        self.assertNotIn('proj:epsg', json_data)
        self.assertNotIn('description', json_data)
        self.assertNotIn('title', json_data)
        self.assertNotIn('file:checksum', json_data)

    def test_asset_upsert_create(self):
        collection = self.collection
        asset = self.factory.create_collection_asset_sample(
            collection=self.collection, sample='asset-no-checksum', create_asset_file=False
        )
        asset_name = asset['name']

        response = self.client.get(
            reverse_version('collection-asset-detail', args=[collection.name, asset_name])
        )
        # Check that assert does not exist already
        self.assertStatusCode(404, response)

        # Check also, that the asset does not exist in the DB already
        self.assertFalse(
            CollectionAsset.objects.filter(name=asset_name).exists(),
            msg="Collection asset already exists"
        )

        # Now use upsert to create the new asset
        response = self.client.put(
            reverse_version('collection-asset-detail', args=[collection.name, asset_name]),
            data=asset.get_json('put'),
            content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.assertLocationHeader(
            reverse_version('collection-asset-detail', args=[collection.name, asset_name]),
            response
        )
        self.check_stac_collection_asset(asset.json, json_data, collection.name)

        # make sure that all optional fields are present
        self.assertIn('proj:epsg', json_data)
        self.assertIn('description', json_data)
        self.assertIn('title', json_data)

        # Checksum multihash is set by the AssetUpload later on
        self.assertNotIn('file:checksum', json_data)

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_collection_asset(asset.json, json_data, collection.name)

    def test_asset_upsert_create_non_existing_parent_collection_in_path(self):
        asset = self.factory.create_collection_asset_sample(
            collection=self.collection, create_asset_file=False
        )
        asset_name = asset['name']

        path = (f'/{STAC_BASE_V}/collections/non-existing-collection/assets/'
                f'{asset_name}')

        # Check that asset does not exist already
        response = self.client.get(path)
        self.assertStatusCode(404, response)

        # Check also, that the asset does not exist in the DB already
        self.assertFalse(
            CollectionAsset.objects.filter(name=asset_name).exists(),
            msg="Deleted colelction asset still found in DB"
        )

        # Now use upsert to create the new asset
        response = self.client.put(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(404, response)

    def test_asset_upsert_create_empty_string(self):
        collection_name = self.collection.name
        asset = self.factory.create_collection_asset_sample(
            collection=self.collection, required_only=True, description='', title=''
        )

        path = \
            f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset["name"]}'
        response = self.client.put(
            path, data=asset.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        json_data = response.json()
        for field in ['description', 'title']:
            self.assertIn(field, json_data['description'], msg=f'Field {field} error missing')

    def invalid_request_wrapper(self, sample_name, expected_error_messages, **extra_params):
        collection_name = self.collection.name
        asset = self.factory.create_collection_asset_sample(
            collection=self.collection, sample=sample_name, **extra_params
        )

        path = \
            f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset["name"]}'
        response = self.client.put(
            path, data=asset.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            expected_error_messages,
            response.json()['description'],
            msg='Unexpected error message',
        )

        # Make sure that the asset is not found in DB
        self.assertFalse(
            CollectionAsset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    def test_asset_upsert_create_invalid_data(self):
        self.invalid_request_wrapper(
            'asset-invalid', {
                'proj:epsg': ['A valid integer is required.'],
                'type': ['Invalid media type "dummy"']
            }
        )

    def test_asset_upsert_create_invalid_type(self):
        media_type_str = "image/tiff; application=Geotiff; profile=cloud-optimized"
        self.invalid_request_wrapper(
            'asset-invalid-type', {'type': [f'Invalid media type "{media_type_str}"']}
        )

    def test_asset_upsert_create_type_extension_mismatch(self):
        media_type_str = "application/gml+xml"
        self.invalid_request_wrapper(
            'asset-invalid-type',
            {
                'non_field_errors': [
                    f"Invalid id extension '.tiff', id must match its media type {media_type_str}"
                ]
            },
            media_type=media_type_str,
            # must be overridden, else extension will automatically match the type
            name='asset-invalid-type.tiff'
        )


@override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
class CollectionAssetsUpdateEndpointAssetFileTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample(db_create=True)
        self.asset = self.factory.create_collection_asset_sample(
            collection=self.collection.model, db_create=True
        )
        self.client = Client(headers=get_auth_headers())
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_endpoint_patch_put_href(self):
        collection_name = self.collection['name']
        asset_name = self.asset['name']
        asset_sample = self.asset.copy()

        put_payload = asset_sample.get_json('put')
        put_payload['href'] = 'https://testserver/non-existing-asset'
        patch_payload = {'href': 'https://testserver/non-existing-asset'}

        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.patch(path, data=patch_payload, content_type="application/json")
        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "Found read-only property in payload",
            description['href'][0],
            msg="Unexpected error message"
        )

        response = self.client.put(path, data=put_payload, content_type="application/json")
        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "Found read-only property in payload",
            description['href'][0],
            msg="Unexpected error message"
        )


@override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
class CollectionAssetsUpdateEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample(db_create=True)
        self.asset = self.factory.create_collection_asset_sample(
            collection=self.collection.model, db_create=True
        )
        self.client = Client(headers=get_auth_headers())
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_endpoint_put(self):
        collection_name = self.collection['name']
        asset_name = self.asset['name']
        changed_asset = self.factory.create_collection_asset_sample(
            collection=self.collection.model,
            name=asset_name,
            sample='asset-1-updated',
            media_type=self.asset['media_type'],
            checksum_multihash=self.asset['checksum_multihash'],
            create_asset_file=False
        )

        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.put(
            path, data=changed_asset.get_json('put'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_collection_asset(changed_asset.json, json_data, collection_name)

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_collection_asset(changed_asset.json, json_data, collection_name)

    def test_asset_endpoint_put_extra_payload(self):
        collection_name = self.collection['name']
        asset_name = self.asset['name']
        changed_asset = self.factory.create_collection_asset_sample(
            collection=self.collection.model,
            name=asset_name,
            sample='asset-1-updated',
            media_type=self.asset['media_type'],
            checksum_multihash=self.asset['checksum_multihash'],
            extra_attribute='not allowed',
            create_asset_file=False
        )

        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.put(
            path, data=changed_asset.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'extra_attribute': ['Unexpected property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_asset_endpoint_put_read_only_in_payload(self):
        collection_name = self.collection['name']
        asset_name = self.asset['name']
        changed_asset = self.factory.create_collection_asset_sample(
            collection=self.collection.model,
            name=asset_name,
            sample='asset-1-updated',
            media_type=self.asset['media_type'],
            created=utc_aware(datetime.utcnow()),
            create_asset_file=False,
            checksum_multihash=self.asset['checksum_multihash'],
        )

        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.put(
            path,
            data=changed_asset.get_json('put', keep_read_only=True),
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual({
            'created': ['Found read-only property in payload'],
            'file:checksum': ['Found read-only property in payload']
        },
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_asset_endpoint_put_rename_asset(self):
        # rename should not be allowed
        collection_name = self.collection['name']
        asset_name = self.asset['name']
        new_asset_name = "new-asset-name.tif"
        changed_asset = self.asset.copy()
        changed_asset['name'] = new_asset_name

        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.put(
            path, data=changed_asset.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'id': 'Renaming is not allowed'},
                         response.json()['description'],
                         msg='Unexpected error message')

        # Check the data by reading it back
        response = self.client.get(
            f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        )
        json_data = response.json()
        self.assertStatusCode(200, response)

        self.assertEqual(asset_name, json_data['id'])

        # Check the data that no new entry exist
        response = self.client.get(
            f'/{STAC_BASE_V}/collections/{collection_name}/assets/{new_asset_name}'
        )

        # 404 - not found
        self.assertStatusCode(404, response)

    def test_asset_endpoint_patch_rename_asset(self):
        # rename should not be allowed
        collection_name = self.collection['name']
        asset_name = self.asset['name']
        new_asset_name = "new-asset-name.tif"

        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.patch(
            path, data={"id": new_asset_name}, content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'id': 'Renaming is not allowed'},
                         response.json()['description'],
                         msg='Unexpected error message')

        # Check the data by reading it back
        response = self.client.get(
            f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        )
        json_data = response.json()
        self.assertStatusCode(200, response)

        self.assertEqual(asset_name, json_data['id'])

        # Check the data that no new entry exist
        response = self.client.get(
            f'/{STAC_BASE_V}/collections/{collection_name}/assets/{new_asset_name}'
        )

        # 404 - not found
        self.assertStatusCode(404, response)

    def test_asset_endpoint_put_change_content_type(self):
        # Changing content-type is not allowed because we would need to re-upload the asset file
        # in order to update it on the file on S3
        collection_name = self.collection['name']
        asset_name = self.asset['name']
        new_asset_type = "image/tiff; application=geotiff"
        changed_asset = self.asset.copy()
        changed_asset['media_type'] = new_asset_type

        self.assertNotEqual(
            self.asset['media_type'], new_asset_type, msg="Asset media type is already identical"
        )

        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'

        response = self.client.get(path)
        self.assertStatusCode(200, response, msg="Asset don't exists yet")
        response = self.client.put(
            path, data=changed_asset.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(400, response, msg="Changing asset type should not be allowed")
        self.assertEqual(
            {
                'type': [
                    'Type field cannot be edited. You need to delete and recreate the '
                    'asset with the correct type'
                ]
            },
            response.json()['description'],
            msg='Unexpected error message',
        )

        # Check the data by reading it back
        response = self.client.get(
            f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        )
        json_data = response.json()
        self.assertStatusCode(200, response, msg="Cannot read the asset back to verify")

        self.assertEqual(
            self.asset['media_type'], json_data['type'], msg="Asset type should not have changed"
        )

    def test_asset_endpoint_patch_change_content_type(self):
        # Changing content-type is not allowed because we would need to re-upload the asset file
        # in order to update it on the file on S3
        collection_name = self.collection['name']
        asset_name = self.asset['name']
        new_asset_type = "image/tiff; application=geotiff"

        self.assertNotEqual(
            self.asset['media_type'], new_asset_type, msg="Asset media type is already identical"
        )

        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'

        response = self.client.get(path)
        self.assertStatusCode(200, response, msg="Asset don't exists yet")
        response = self.client.patch(
            path, data={"type": new_asset_type}, content_type="application/json"
        )
        self.assertStatusCode(400, response, msg="Changing asset type should not be allowed")
        self.assertEqual(
            {
                'type': [
                    'Type field cannot be edited. You need to delete and recreate the '
                    'asset with the correct type'
                ]
            },
            response.json()['description'],
            msg='Unexpected error message',
        )

        # Check the data by reading it back
        response = self.client.get(
            f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        )
        json_data = response.json()
        self.assertStatusCode(200, response, msg="Cannot read the asset back to verify")

        self.assertEqual(
            self.asset['media_type'], json_data['type'], msg="Asset type should not have changed"
        )

    def test_asset_endpoint_patch_extra_payload(self):
        collection_name = self.collection['name']
        asset_name = self.asset['name']
        changed_asset = self.factory.create_collection_asset_sample(
            collection=self.collection.model,
            name=asset_name,
            sample='asset-1-updated',
            media_type=self.asset['media_type'],
            extra_payload='invalid'
        )

        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.patch(
            path, data=changed_asset.get_json('patch'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'extra_payload': ['Unexpected property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_asset_endpoint_patch_read_only_in_payload(self):
        collection_name = self.collection['name']
        asset_name = self.asset['name']
        changed_asset = self.factory.create_collection_asset_sample(
            collection=self.collection.model,
            name=asset_name,
            sample='asset-1-updated',
            media_type=self.asset['media_type'],
            created=utc_aware(datetime.utcnow())
        )

        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.patch(
            path,
            data=changed_asset.get_json('patch', keep_read_only=True),
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'created': ['Found read-only property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_asset_atomic_upsert_create_500(self):
        sample = self.factory.create_collection_asset_sample(
            self.collection.model, create_asset_file=True
        )

        # the dataset to update does not exist yet
        with self.settings(DEBUG_PROPAGATE_API_EXCEPTIONS=True), disableLogger('stac_api.apps'):
            response = self.client.put(
                reverse(
                    'test-collection-asset-detail-http-500',
                    args=[self.collection['name'], sample['name']]
                ),
                data=sample.get_json('put'),
                content_type='application/json'
            )
        self.assertStatusCode(500, response)
        self.assertEqual(response.json()['description'], "AttributeError('test exception')")

        # Make sure that the ressource has not been created
        response = self.client.get(
            reverse_version(
                'collection-asset-detail', args=[self.collection['name'], sample['name']]
            )
        )
        self.assertStatusCode(404, response)

    def test_asset_atomic_upsert_update_500(self):
        sample = self.factory.create_collection_asset_sample(
            self.collection.model, name=self.asset['name'], create_asset_file=True
        )

        # Make sure samples is different from actual data
        self.assertNotEqual(sample.attributes, self.asset.attributes)

        # the dataset to update does not exist yet
        with self.settings(DEBUG_PROPAGATE_API_EXCEPTIONS=True), disableLogger('stac_api.apps'):
            # because we explicitely test a crash here we don't want to print a CRITICAL log on the
            # console therefore disable it.
            response = self.client.put(
                reverse(
                    'test-collection-asset-detail-http-500',
                    args=[self.collection['name'], sample['name']]
                ),
                data=sample.get_json('put'),
                content_type='application/json'
            )
        self.assertStatusCode(500, response)
        self.assertEqual(response.json()['description'], "AttributeError('test exception')")

        # Make sure that the ressource has not been created
        response = self.client.get(
            reverse_version(
                'collection-asset-detail', args=[self.collection['name'], sample['name']]
            )
        )
        self.assertStatusCode(200, response)
        self.check_stac_collection_asset(
            self.asset.json, response.json(), self.collection['name'], ignore=['item']
        )


@override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
class CollectionAssetRaceConditionTest(StacBaseTransactionTestCase):

    def setUp(self):
        self.auth_headers = get_auth_headers()
        self.factory = Factory()
        self.collection_sample = self.factory.create_collection_sample(
            sample='collection-2', db_create=True
        )

    def test_asset_upsert_race_condition(self):
        workers = 5
        status_201 = 0
        asset_sample = self.factory.create_collection_asset_sample(
            self.collection_sample.model,
            sample='asset-no-checksum',
        )

        def asset_atomic_upsert_test(worker):
            # This method runs on separate thread therefore it requires to create a new client
            # for each call.
            client = Client(headers=self.auth_headers)
            return client.put(
                reverse_version(
                    'collection-asset-detail',
                    args=[self.collection_sample['name'], asset_sample['name']]
                ),
                data=asset_sample.get_json('put'),
                content_type='application/json'
            )

        # We call the PUT asset several times in parallel with the same data to make sure
        # that we don't have any race condition.
        responses, errors = self.run_parallel(workers, asset_atomic_upsert_test)

        for worker, response in responses:
            if response.status_code == 201:
                status_201 += 1
            self.assertIn(
                response.status_code, [200, 201],
                msg=f'Unexpected response status code {response.status_code} for worker {worker}'
            )
            self.check_stac_collection_asset(
                asset_sample.json, response.json(), self.collection_sample['name'], ignore=['item']
            )
        self.assertEqual(status_201, 1, msg="Not only one upsert did a create !")


@override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
class CollectionAssetsDeleteEndpointTestCase(StacBaseTestCase, S3TestMixin):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.asset = self.factory.create_collection_asset_sample(collection=self.collection).model
        self.client = Client(headers=get_auth_headers())
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_endpoint_delete_asset(self):
        collection_name = self.collection.name
        asset_name = self.asset.name
        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        s3_path = get_collection_asset_path(self.collection, asset_name)
        self.assertS3ObjectExists(s3_path)
        response = self.client.delete(path)
        self.assertStatusCode(200, response)

        # Check that is has really been deleted
        self.assertS3ObjectNotExists(s3_path)
        response = self.client.get(path)
        self.assertStatusCode(404, response)

        # Check that it is really not to be found in DB
        self.assertFalse(
            CollectionAsset.objects.filter(name=self.asset.name).exists(),
            msg="Deleted asset still found in DB"
        )

    def test_asset_endpoint_delete_asset_invalid_name(self):
        collection_name = self.collection.name
        path = f"/{STAC_BASE_V}/collections/{collection_name}/assets/non-existent-asset"
        response = self.client.delete(path)
        self.assertStatusCode(404, response)


class CollectionAssetsEndpointUnauthorizedTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.asset = self.factory.create_collection_asset_sample(collection=self.collection).model
        self.client = Client()

    def test_unauthorized_asset_post_put_patch_delete(self):
        collection_name = self.collection.name
        asset_name = self.asset.name

        new_asset = self.factory.create_collection_asset_sample(collection=self.collection).json
        updated_asset = self.factory.create_collection_asset_sample(
            collection=self.collection, name=asset_name, sample='asset-1-updated'
        ).get_json('post')

        # make sure POST fails for anonymous user:
        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets'
        response = self.client.post(path, data=new_asset, content_type="application/json")
        self.assertStatusCode(401, response, msg="Unexpected status.")

        # make sure PUT fails for anonymous user:

        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.put(path, data=updated_asset, content_type="application/json")
        self.assertStatusCode(401, response, msg="Unexpected status.")

        # make sure PATCH fails for anonymous user:
        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.patch(path, data=updated_asset, content_type="application/json")
        self.assertStatusCode(401, response, msg="Unexpected status.")

        # make sure DELETE fails for anonymous user:
        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.delete(path)
        self.assertStatusCode(401, response, msg="Unexpected status.")


class CollectionAssetsDisabledAuthenticationEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.asset = self.factory.create_collection_asset_sample(collection=self.collection).model
        self.client = Client()
        self.username = 'SherlockHolmes'
        self.password = '221B_BakerStreet'
        self.user = get_user_model().objects.create_superuser(
            self.username, 'top@secret.co.uk', self.password
        )

    def run_test(self, status, headers=None):
        collection_name = self.collection.name
        asset_name = self.asset.name

        # PUT
        path = f'/{STAC_BASE_V}/collections/{collection_name}/assets/{asset_name}'
        response = self.client.put(path, headers=headers, data={}, content_type="application/json")
        self.assertStatusCode(status, response, msg="Unauthorized put was permitted.")

        # PATCH
        response = self.client.patch(
            path, headers=headers, data={}, content_type="application/json"
        )
        self.assertStatusCode(status, response, msg="Unauthorized patch was permitted.")

        # DELETE
        response = self.client.delete(path, headers=headers)
        self.assertStatusCode(status, response, msg="Unauthorized del was permitted.")

    @override_settings(FEATURE_AUTH_RESTRICT_V1=False)
    def test_enabled_session_authentication(self):
        self.client.login(username=self.username, password=self.password)
        self.run_test([200, 400])

    @override_settings(FEATURE_AUTH_RESTRICT_V1=False)
    def test_enabled_token_authentication(self):
        token = Token.objects.create(user=self.user)
        headers = {'Authorization': f'Token {token.key}'}
        self.run_test([200, 400], headers=headers)

    @override_settings(FEATURE_AUTH_RESTRICT_V1=False)
    def test_enabled_base_authentication(self):
        token = b64encode(f'{self.username}:{self.password}'.encode()).decode()
        headers = {'Authorization': f'Basic {token}'}
        self.run_test([200, 400], headers=headers)

    @override_settings(FEATURE_AUTH_RESTRICT_V1=True)
    def test_disabled_session_authentication(self):
        self.client.login(username=self.username, password=self.password)
        self.run_test(401)

    @override_settings(FEATURE_AUTH_RESTRICT_V1=True)
    def test_disabled_token_authentication(self):
        token = Token.objects.create(user=self.user)
        headers = {'Authorization': f'Token {token.key}'}
        self.run_test(401, headers=headers)

    @override_settings(FEATURE_AUTH_RESTRICT_V1=True)
    def test_disabled_base_authentication(self):
        token = b64encode(f'{self.username}:{self.password}'.encode()).decode()
        headers = {'Authorization': f'Basic {token}'}
        self.run_test(401, headers=headers)
