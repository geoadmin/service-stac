import logging
from datetime import datetime
from json import dumps
from json import loads
from pprint import pformat

from django.conf import settings
from django.test import Client

from stac_api.models import Asset
from stac_api.utils import get_sha256_multihash
from stac_api.utils import utc_aware

from tests.base_test import StacBaseTestCase
from tests.data_factory import Factory
from tests.utils import client_login
from tests.utils import mock_s3_asset_file
from tests.utils import upload_file_on_s3

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
        self.asset_1 = self.factory.create_asset_sample(item=self.item, db_create=True)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_assets_endpoint(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_2 = self.factory.create_asset_sample(item=self.item, sample='asset-2', db_create=True)
        asset_3 = self.factory.create_asset_sample(item=self.item, sample='asset-3', db_create=True)
        response = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_name}/assets"
        )
        self.assertStatusCode(200, response)
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        self.assertIn('assets', json_data, msg='assets is missing in response')
        self.assertEqual(
            3, len(json_data['assets']), msg='Number of assets doen\'t match the expected'
        )
        for i, asset in enumerate([self.asset_1, asset_2, asset_3]):
            self.check_stac_asset(
                asset.json, json_data['assets'][i], collection_name, item_name, ignore=['item']
            )

    def test_assets_endpoint_collection_does_not_exist(self):
        collection_name = "non-existent"
        item_name = self.item.name
        response = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_name}/assets"
        )
        self.assertStatusCode(404, response)

    def test_assets_endpoint_item_does_not_exist(self):
        collection_name = self.collection.name
        item_name = "non-existent"
        response = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_name}/assets"
        )
        self.assertStatusCode(404, response)

    def test_single_asset_endpoint(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset_1["name"]
        response = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        self.check_stac_asset(
            self.asset_1.json, json_data, collection_name, item_name, ignore=['item']
        )

        # The ETag change between each test call due to the created, updated time that are in the
        # hash computation of the ETag
        self.check_header_etag(None, response)


class AssetsWriteEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.client = Client()
        client_login(self.client)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_endpoint_post_only_required(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(
            item=self.item, required_only=True, create_asset_file=True, file=b'Dummy file content'
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.check_header_location(f"{path}/{asset['name']}", response)
        self.check_stac_asset(asset.json, json_data, collection_name, item_name, ignore=['item'])

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(asset.json, json_data, collection_name, item_name, ignore=['item'])

        # make sure that the optional fields are not present
        self.assertNotIn('geoadmin:lang', json_data)
        self.assertNotIn('geoadmin:variant', json_data)
        self.assertNotIn('proj:epsg', json_data)
        self.assertNotIn('eo:gsd', json_data)
        self.assertNotIn('description', json_data)
        self.assertNotIn('title', json_data)

    def test_asset_endpoint_post_full(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item, create_asset_file=True)

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.check_header_location(f"{path}/{asset['name']}", response)
        self.check_stac_asset(asset.json, json_data, collection_name, item_name, ignore=['item'])

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(asset.json, json_data, collection_name, item_name, ignore=['item'])

    def test_asset_endpoint_post_empty_string(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(
            item=self.item,
            required_only=True,
            description='',
            geoadmin_variant='',
            geoadmin_lang='',
            title='',
            create_asset_file=True
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        json_data = response.json()
        for field in ['description', 'title', 'geoadmin:lang', 'geoadmin:variant']:
            self.assertIn(field, json_data['description'], msg=f'Field {field} error missing')

    def test_asset_endpoint_post_extra_payload(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(
            item=self.item, extra_attribute='not allowed', create_asset_file=True
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'extra_attribute': ['Unexpected property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    def test_asset_endpoint_post_read_only_in_payload(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(
            item=self.item, created=utc_aware(datetime.utcnow()), create_asset_file=True
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post', keep_read_only=True), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            {
                'created': ['Found read-only property in payload'],
                'href': ['Found read-only property in payload']
            },
            response.json()['description'],
            msg='Unexpected error message',
        )

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    def test_asset_endpoint_post_read_only_href_in_payload(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(
            item=self.item, href='https://testserver/test.txt', create_asset_file=True
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post', keep_read_only=True), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "Found read-only property in payload",
            description['href'][0],
            msg="Unexpected error message"
        )

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    def test_asset_endpoint_post_invalid_data(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(
            item=self.item, sample='asset-invalid', create_asset_file=True
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            {
                'eo:gsd': ['A valid number is required.'],
                'geoadmin:lang': ['"12" is not a valid choice.'],
                'proj:epsg': ['A valid integer is required.'],
                'type': ['"dummy" is not a valid choice.']
            },
            response.json()['description'],
            msg='Unexpected error message',
        )

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    def test_asset_endpoint_post_characters_geoadmin_variant(self):
        # valid geoadmin:variant
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(
            item=self.item, sample='asset-valid-geoadmin-variant', create_asset_file=True
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(201, response)

        # invalid geoadmin:variant
        asset = self.factory.create_asset_sample(
            item=self.item, sample='asset-invalid-geoadmin-variant', create_asset_file=True
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            {
                'geoadmin:variant': [
                    'Invalid geoadmin:variant "more than twenty-five characters with s", '
                    'special characters beside one space are not allowed',
                    'Ensure this field has no more than 25 characters.'
                ]
            },
            response.json()['description'],
            msg='Unexpected error message',
        )


class AssetsWriteEndpointAssetFileTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.client = Client()
        client_login(self.client)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_endpoint_post_asset_file_dont_exists(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item, create_asset_file=False)

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "Asset doesn't exists at href http://testserver/collection-1/item-1/asset-1",
            description['href'][0],
            msg="Unexpected error message"
        )

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    # NOTE: Unfortunately this test cannot be done with the moto mocking.
    # def test_asset_endpoint_post_s3_not_answering(self):
    #     collection_name = self.collection.name
    #     item_name = self.item.name
    #     asset = self.factory.create_asset_sample(item=self.item)

    #     path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
    #     response = self.client.post(
    #         path, data=asset.get_json('post'), content_type="application/json"
    #     )
    #     self.assertStatusCode(400, response)
    #     description = response.json()['description']
    #     self.assertIn('href', description, msg=f'Unexpected field error {description}')
    #     self.assertEqual(
    #         "href location not responding", description['href'][0], msg="Unexpected error message"
    #     )

    #     # Make sure that the asset is not found in DB
    #     self.assertFalse(
    #         Asset.objects.filter(name=asset.json['id']).exists(),
    #         msg="Invalid asset has been created in DB"
    #     )

    def test_asset_endpoint_post_s3_without_sha256(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item, create_asset_file=False)

        upload_file_on_s3(
            f'{collection_name}/{item_name}/{asset["name"]}', asset["file"], params={}
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(
            path, data=asset.get_json('post'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('non_field_errors', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "Asset at href http://testserver/collection-1/item-1/asset-1 has a md5 multihash while "
            "a sha2-256 multihash is defined in the checksum:multihash attribute",
            description['non_field_errors'][0],
            msg="Unexpected error message"
        )

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )

    def test_asset_endpoint_post_wrong_checksum(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset = self.factory.create_asset_sample(item=self.item, create_asset_file=True)
        asset_json = asset.get_json('post')
        asset_json['checksum:multihash'] = get_sha256_multihash(
            b'new dummy content that do not match real checksum'
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(path, data=asset_json, content_type="application/json")
        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('non_field_errors', description, msg=f'Unexpected field error {description}')
        self.assertEqual(
            "Asset at href http://testserver/collection-1/item-1/asset-1 with sha2-256 hash "
            "a7f5e7ca03b0f80a2fcfe5142642377e7654df2dfa736fe4d925322d8a651efe doesn't match the "
            "checksum:multihash 3db85f41709d08bf1f2907042112bf483b28e12db4b3ffb5428a1f28308847ba",
            description['non_field_errors'][0],
            msg="Unexpected error message"
        )

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=asset.json['id']).exists(),
            msg="Invalid asset has been created in DB"
        )


class AssetsUpdateEndpointAssetFileTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample(db_create=True)
        self.item = self.factory.create_item_sample(
            collection=self.collection.model, db_create=True
        )
        self.asset = self.factory.create_asset_sample(item=self.item.model, db_create=True)
        self.client = Client()
        client_login(self.client)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_endpoint_patch_checksum(self):
        new_file_content = b'New file content'
        new_multihash = get_sha256_multihash(new_file_content)
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = self.asset['name']

        # upload first a new file on S3
        upload_file_on_s3(f'{collection_name}/{item_name}/{asset_name}', new_file_content)

        patch_payload = {'checksum:multihash': new_multihash}
        patch_asset = self.asset.copy()
        patch_asset['checksum_multihash'] = new_multihash

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.patch(path, data=patch_payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.check_stac_asset(
            patch_asset.json, json_data, collection_name, item_name, ignore=['item']
        )

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(
            patch_asset.json, json_data, collection_name, item_name, ignore=['item']
        )

    def test_asset_endpoint_patch_put_href(self):
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = self.asset['name']
        asset_sample = self.asset.copy()

        put_payload = asset_sample.get_json('put')
        put_payload['href'] = 'https://testserver/non-existing-asset'
        patch_payload = {'href': 'https://testserver/non-existing-asset'}

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
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


class AssetsUpdateEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample(db_create=True)
        self.item = self.factory.create_item_sample(
            collection=self.collection.model, db_create=True
        )
        self.asset = self.factory.create_asset_sample(item=self.item.model, db_create=True)
        self.client = Client()
        client_login(self.client)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_put_dont_exists(self):
        collection_name = self.collection['name']
        item_name = self.item['name']
        payload_json = self.factory.create_asset_sample(
            item=self.item.model, sample='asset-2', create_asset_file=False
        ).get_json('put')

        # the dataset to update does not exist yet
        path = \
          f"/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{payload_json['id']}"
        response = self.client.put(path, data=payload_json, content_type='application/json')
        self.assertStatusCode(404, response)

    def test_asset_endpoint_put(self):
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = self.asset['name']
        changed_asset = self.factory.create_asset_sample(
            item=self.item.model,
            name=asset_name,
            sample='asset-1-updated',
            checksum_multihash=self.asset['checksum_multihash'],
            create_asset_file=False
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.put(
            path, data=changed_asset.get_json('put'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(
            changed_asset.json, json_data, collection_name, item_name, ignore=['item']
        )

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(
            changed_asset.json, json_data, collection_name, item_name, ignore=['item']
        )

    def test_asset_endpoint_put_extra_payload(self):
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = self.asset['name']
        changed_asset = self.factory.create_asset_sample(
            item=self.item.model,
            name=asset_name,
            sample='asset-1-updated',
            checksum_multihash=self.asset['checksum_multihash'],
            extra_attribute='not allowed',
            create_asset_file=False
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.put(
            path, data=changed_asset.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'extra_attribute': ['Unexpected property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_asset_endpoint_put_read_only_in_payload(self):
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = self.asset['name']
        changed_asset = self.factory.create_asset_sample(
            item=self.item.model,
            name=asset_name,
            checksum_multihash=self.asset['checksum_multihash'],
            sample='asset-1-updated',
            created=utc_aware(datetime.utcnow()),
            create_asset_file=False
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.put(
            path,
            data=changed_asset.get_json('put', keep_read_only=True),
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'created': ['Found read-only property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_asset_endpoint_put_rename_asset(self):
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = self.asset['name']
        new_asset_name = "new-asset-name"
        changed_asset = self.factory.create_asset_sample(
            item=self.item.model,
            name=new_asset_name,
            sample='asset-1-updated',
            checksum_multihash=self.asset['checksum_multihash']
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.put(
            path, data=changed_asset.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(changed_asset.json['id'], json_data['id'])
        self.check_stac_asset(
            changed_asset.json, json_data, collection_name, item_name, ignore=['item']
        )

        # Check the data by reading it back
        response = self.client.get(
            f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{new_asset_name}'
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(
            changed_asset.json, json_data, collection_name, item_name, ignore=['item']
        )

    def test_asset_endpoint_patch_rename_asset(self):
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = self.asset['name']
        new_asset_name = "new-asset-name"
        changed_asset = self.factory.create_asset_sample(
            item=self.item.model, name=new_asset_name, sample='asset-1-updated'
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.patch(
            path, data=changed_asset.get_json('patch'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(changed_asset.json['id'], json_data['id'])
        self.check_stac_asset(
            changed_asset.json, json_data, collection_name, item_name, ignore=['item']
        )

        # Check the data by reading it back
        response = self.client.get(
            f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{new_asset_name}'
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(changed_asset.json['id'], json_data['id'])
        self.check_stac_asset(
            changed_asset.json, json_data, collection_name, item_name, ignore=['item']
        )

    def test_asset_endpoint_patch_extra_payload(self):
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = self.asset['name']
        changed_asset = self.factory.create_asset_sample(
            item=self.item.model,
            name=asset_name,
            sample='asset-1-updated',
            extra_payload='invalid'
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.patch(
            path, data=changed_asset.get_json('patch'), content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'extra_payload': ['Unexpected property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_asset_endpoint_patch_read_only_in_payload(self):
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = self.asset['name']
        changed_asset = self.factory.create_asset_sample(
            item=self.item.model,
            name=asset_name,
            sample='asset-1-updated',
            created=utc_aware(datetime.utcnow())
        )

        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.patch(
            path,
            data=changed_asset.get_json('patch', keep_read_only=True),
            content_type="application/json"
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'created': ['Found read-only property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')


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
