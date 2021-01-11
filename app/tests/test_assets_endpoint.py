import logging
from datetime import datetime
from json import dumps
from json import loads
from pprint import pformat

import requests
import requests_mock

from django.conf import settings
from django.test import Client

from stac_api.models import Asset
from stac_api.serializers import AssetSerializer
from stac_api.utils import fromisoformat
from stac_api.utils import get_sha256_multihash
from stac_api.utils import utc_aware

from tests.base_test import StacBaseTestCase
from tests.data_factory import Factory
from tests.utils import client_login
from tests.utils import mock_requests_asset_file
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


def to_dict(input_ordered_dict):
    return loads(dumps(input_ordered_dict))


class AssetsEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.asset_1 = self.factory.create_asset_sample(item=self.item).model
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_assets_endpoint(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_2 = self.factory.create_asset_sample(item=self.item, sample='asset-2').model
        asset_3 = self.factory.create_asset_sample(item=self.item, sample='asset-3').model
        response = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_name}/assets"
        )
        self.assertStatusCode(200, response)
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        # Check that the answer is equal to the initial data
        serializer = AssetSerializer([self.asset_1, asset_2, asset_3],
                                     many=True,
                                     context={'request': response.wsgi_request})
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            original_data, json_data, msg="Returned data does not match expected data"
        )

    def test_single_asset_endpoint(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset_1.name
        response = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        # The ETag change between each test call due to the created, updated time that are in the
        # hash computation of the ETag
        self.check_header_etag(None, response)

        # Check that the answer is equal to the initial data
        serializer = AssetSerializer(self.asset_1, context={'request': response.wsgi_request})
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            original_data, json_data, msg="Returned data does not match expected data"
        )
        # created and updated must exist and be a valid date
        date_fields = ['created', 'updated']
        for date_field in date_fields:
            self.assertTrue(
                fromisoformat(json_data[date_field]),
                msg=f"The field {date_field} has an invalid date"
            )


@requests_mock.Mocker(kw='requests_mocker')
class AssetsWriteEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.client = Client()
        client_login(self.client)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_endpoint_post_only_required(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item, required_only=True)

        mock_requests_asset_file(requests_mocker, asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.check_header_location(f"{path}/{asset['name']}", response)
        self.check_stac_asset(asset.json, json_data, ignore=['item'])

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(asset.json, json_data, ignore=['item'])

    def test_asset_endpoint_post_full(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item)

        mock_requests_asset_file(requests_mocker, asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.check_header_location(f"{path}/{asset['name']}", response)
        self.check_stac_asset(asset.json, json_data, ignore=['item'])

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(asset.json, json_data, ignore=['item'])

    def test_asset_endpoint_post_extra_payload(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item, extra_attribute='not allowed')

        mock_requests_asset_file(requests_mocker, asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    def test_asset_endpoint_post_read_only_in_payload(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(
            item=self.item, created=utc_aware(datetime.utcnow())
        )

        mock_requests_asset_file(requests_mocker, asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    def test_asset_endpoint_post_invalid_data(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item, sample='asset-invalid')

        mock_requests_asset_file(requests_mocker, asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )


@requests_mock.Mocker(kw='requests_mocker')
class AssetsWriteEndpointAssetFileTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.client = Client()
        client_login(self.client)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_endpoint_post_asset_file_dont_exists(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item)

        mock_requests_asset_file(
            requests_mocker, asset, headers={'x-amz-meta-sha256': None}, status_code=404
        )
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "Asset doesn't exists at href", description['href'][0], msg="Unexpected error message"
        )

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    def test_asset_endpoint_post_s3_not_answering(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item)

        mock_requests_asset_file(requests_mocker, asset, exc=requests.exceptions.ConnectTimeout)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "href location not responding", description['href'][0], msg="Unexpected error message"
        )

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    def test_asset_endpoint_post_s3_without_sha256(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item)

        mock_requests_asset_file(requests_mocker, asset, headers={'x-amz-meta-sha256': None})
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(500, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "Asset at href http://testserver/collection-1/item-1/asset-1 doesn't provide a valid "
            "checksum header (ETag or x-amz-meta-sha256) for validation",
            description['href'],
            msg="Unexpected error message"
        )

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    def test_asset_endpoint_post_wrong_checksum(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item)

        mock_requests_asset_file(
            requests_mocker, asset, headers={'x-amz-meta-sha256': get_sha256_multihash(b'')[4:]}
        )
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('non_field_errors', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "Asset at href http://testserver/collection-1/item-1/asset-1 with sha2-256 hash "
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 don't match expected "
            "hash a7f5e7ca03b0f80a2fcfe5142642377e7654df2dfa736fe4d925322d8a651efe",
            description['non_field_errors'][0],
            msg="Unexpected error message"
        )

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )


@requests_mock.Mocker(kw='requests_mocker')
class AssetsUpdateEndpointAssetFileTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.asset = self.factory.create_asset_sample(item=self.item).model
        self.client = Client()
        client_login(self.client)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_endpoint_patch_checksum(self, requests_mocker):
        new_multihash = get_sha256_multihash(b'New file content')
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        asset_sample = self.factory.create_asset_sample(
            item=self.item, name=asset_name, required_only=True, checksum_multihash=new_multihash
        )

        patch_payload = {'checksum:multihash': new_multihash}

        mock_requests_asset_file(requests_mocker, asset_sample)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.patch(path, data=patch_payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.check_stac_asset(asset_sample.json, json_data, ignore=['item'])

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(asset_sample.json, json_data, ignore=['item'])

    def test_asset_endpoint_patch_put_href(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        asset_sample = self.factory.create_asset_sample(
            item=self.item, name=asset_name, required_only=True, href='https://www.google.com'
        )

        patch_payload = {'href': 'https://www.google.com'}

        mock_requests_asset_file(requests_mocker, asset_sample)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.patch(path, data=patch_payload, content_type="application/json")
        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "Unexpected property in payload",
            description['href'][0],
            msg="Unexpected error message"
        )

        response = self.client.put(
            path, data=asset_sample.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "Unexpected property in payload",
            description['href'][0],
            msg="Unexpected error message"
        )


@requests_mock.Mocker(kw='requests_mocker')
class AssetsUpdateEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.asset = self.factory.create_asset_sample(item=self.item).model
        self.client = Client()
        client_login(self.client)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_put_dont_exists(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        payload_json = self.factory.create_asset_sample(item=self.item,
                                                        sample='asset-2').get_json('put')

        # the dataset to update does not exist yet
        path = \
          f"/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{payload_json['id']}"
        response = self.client.put(path, data=payload_json, content_type='application/json')
        self.assertStatusCode(404, response)

    def test_asset_endpoint_put(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        changed_asset = self.factory.create_asset_sample(
            item=self.item,
            name=asset_name,
            sample='asset-1-updated',
            checksum_multihash=self.asset.checksum_multihash
        )

        mock_requests_asset_file(requests_mocker, changed_asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.put(
            path, data=changed_asset.get_json('put'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(changed_asset.json, json_data, ignore=['item'])

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(changed_asset.json, json_data, ignore=['item'])

    def test_asset_endpoint_put_extra_payload(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        changed_asset = self.factory.create_asset_sample(
            item=self.item,
            name=asset_name,
            sample='asset-1-updated',
            checksum_multihash=self.asset.checksum_multihash,
            extra_attribute='not allowed'
        )

        mock_requests_asset_file(requests_mocker, changed_asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.put(
            path, data=changed_asset.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(400, response)

    def test_asset_endpoint_put_read_only_in_payload(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        changed_asset = self.factory.create_asset_sample(
            item=self.item,
            name=asset_name,
            checksum_multihash=self.asset.checksum_multihash,
            sample='asset-1-updated',
            created=utc_aware(datetime.utcnow())
        )

        mock_requests_asset_file(requests_mocker, changed_asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.put(
            path, data=changed_asset.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(400, response)

    def test_asset_endpoint_put_rename_asset(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        new_asset_name = "new-asset-name"
        changed_asset = self.factory.create_asset_sample(
            item=self.item,
            name=new_asset_name,
            sample='asset-1-updated',
            checksum_multihash=self.asset.checksum_multihash
        )

        mock_requests_asset_file(requests_mocker, changed_asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.put(
            path, data=changed_asset.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(changed_asset.json['id'], json_data['id'])
        self.check_stac_asset(changed_asset.json, json_data, ignore=['item'])

        # Check the data by reading it back
        response = self.client.get(
            f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{new_asset_name}'
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(changed_asset.json, json_data, ignore=['item'])

    def test_asset_endpoint_patch_rename_asset(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        new_asset_name = "new-asset-name"
        changed_asset = self.factory.create_asset_sample(
            item=self.item, name=new_asset_name, sample='asset-1-updated'
        )

        mock_requests_asset_file(requests_mocker, changed_asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.patch(
            path, data=changed_asset.get_json('patch'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(changed_asset.json['id'], json_data['id'])
        self.check_stac_asset(changed_asset.json, json_data, ignore=['item'])

        # Check the data by reading it back
        response = self.client.get(
            f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{new_asset_name}'
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(changed_asset.json['id'], json_data['id'])
        self.check_stac_asset(changed_asset.json, json_data, ignore=['item'])

    def test_asset_endpoint_patch_extra_payload(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        changed_asset = self.factory.create_asset_sample(
            item=self.item, name=asset_name, sample='asset-1-updated', extra_payload='invalid'
        )

        mock_requests_asset_file(requests_mocker, changed_asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.patch(
            path, data=changed_asset.get_json('patch'), content_type="application/json"
        )
        self.assertStatusCode(400, response)

    def test_asset_endpoint_patch_read_only_in_payload(self, requests_mocker):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        changed_asset = self.factory.create_asset_sample(
            item=self.item,
            name=asset_name,
            sample='asset-1-updated',
            created=utc_aware(datetime.utcnow())
        )

        mock_requests_asset_file(requests_mocker, changed_asset)
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.patch(
            path, data=changed_asset.get_json('patch'), content_type="application/json"
        )
        self.assertStatusCode(400, response)


class AssetsDeleteEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.asset = self.factory.create_asset_sample(item=self.item).model
        self.client = Client()
        client_login(self.client)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_endpoint_delete_asset(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.delete(path)
        self.assertStatusCode(200, response)

        # Check that is has really been deleted
        response = self.client.get(path)
        self.assertStatusCode(404, response)

        # Check that it is really not to be found in DB
        self.assertFalse(
            Asset.objects.filter(name=self.asset.name).exists(),
            msg="Deleted asset still found in DB"
        )

    def test_asset_endpoint_delete_asset_invalid_name(self):
        collection_name = self.collection.name
        item_name = self.item.name
        path = (
            f"/{API_BASE}/collections/{collection_name}"
            f"/items/{item_name}/assets/non-existent-asset"
        )
        response = self.client.delete(path)
        self.assertStatusCode(404, response)


class AssetsEndpointUnauthorizedTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.asset = self.factory.create_asset_sample(item=self.item).model
        self.client = Client()

    def test_unauthorized_asset_post_put_patch_delete(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name

        new_asset = self.factory.create_asset_sample(item=self.item).json
        updated_asset = self.factory.create_asset_sample(
            item=self.item, name=asset_name, sample='asset-1-updated'
        ).get_json('post')

        # make sure POST fails for anonymous user:
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(path, data=new_asset, content_type="application/json")
        self.assertStatusCode(401, response, msg="Unauthorized post was permitted.")

        # make sure PUT fails for anonymous user:

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.put(path, data=updated_asset, content_type="application/json")
        self.assertStatusCode(401, response, msg="Unauthorized put was permitted.")

        # make sure PATCH fails for anonymous user:
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.patch(path, data=updated_asset, content_type="application/json")
        self.assertStatusCode(401, response, msg="Unauthorized patch was permitted.")

        # make sure DELETE fails for anonymous user:
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.delete(path)
        self.assertStatusCode(401, response, msg="Unauthorized del was permitted.")
