import responses

from django.conf import settings
from django.test import Client

from stac_api.models.item import Asset

from tests.tests_10.base_test import StacBaseTestCase
from tests.tests_10.data_factory import Factory
from tests.tests_10.utils import reverse_version
from tests.utils import client_login
from tests.utils import mock_s3_asset_file


class AssetsExternalAssetEndpointTestCase(StacBaseTestCase):

    @mock_s3_asset_file
    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model
        self.client = Client()
        client_login(self.client)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_create_asset_with_external_url(self):
        collection = self.collection
        item = self.item

        asset_data = {
            'id': 'clouds.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': settings.EXTERNAL_TEST_ASSET_URL
        }

        # create the asset, which isn't allowed
        response = self.client.put(
            reverse_version('asset-detail', args=[collection.name, item.name, asset_data['id']]),
            data=asset_data,
            content_type="application/json"
        )

        self.assertStatusCode(400, response)

        collection.allow_external_assets = True
        collection.external_asset_whitelist = [settings.EXTERNAL_TEST_ASSET_URL]
        collection.save()

        # create the asset, now it's allowed
        response = self.client.put(
            reverse_version('asset-detail', args=[collection.name, item.name, asset_data['id']]),
            data=asset_data,
            content_type="application/json"
        )

        json_data = response.json()
        self.assertStatusCode(201, response)
        self.assertEqual(json_data['href'], asset_data['href'])

        created_asset = Asset.objects.last()
        self.assertEqual(created_asset.file, asset_data['href'])
        self.assertTrue(created_asset.is_external)
        self.assertTrue(created_asset.file_size, -1)

    @responses.activate
    def test_create_asset_validate_external_url(self):
        collection = self.collection
        item = self.item
        external_test_asset_url = 'https://example.com/api/123.jpeg'
        collection.allow_external_assets = True
        collection.external_asset_whitelist = ['https://example.com']
        collection.save()

        # Mock response of external asset url
        responses.add(
            method=responses.GET,
            url=external_test_asset_url,
            body='som',
            status=200,
            content_type='application/json',
            adding_headers={'Content-Length': '3'},
            match=[responses.matchers.header_matcher({"Range": "bytes=0-2"})]
        )

        asset_data = {
            'id': 'clouds.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            # 'href': settings.EXTERNAL_TEST_ASSET_URL
            'href': external_test_asset_url
        }

        # create the asset
        response = self.client.put(
            reverse_version('asset-detail', args=[collection.name, item.name, asset_data['id']]),
            data=asset_data,
            content_type="application/json"
        )

        json_data = response.json()
        self.assertStatusCode(201, response)
        self.assertEqual(json_data['href'], asset_data['href'])

        created_asset = Asset.objects.last()
        self.assertEqual(created_asset.file, asset_data['href'])
        self.assertTrue(created_asset.is_external)
        self.assertTrue(created_asset.file_size, -1)

    @responses.activate
    def test_create_asset_validate_external_url_not_found(self):
        collection = self.collection
        item = self.item
        external_test_asset_url = 'https://example.com/api/123.jpeg'
        collection.allow_external_assets = True
        collection.external_asset_whitelist = ['https://example.com']
        collection.save()

        # Mock response of external asset url returning 404
        responses.add(
            method=responses.GET,
            url=external_test_asset_url,
            body='',
            status=404,
            content_type='application/json',
            adding_headers={'Content-Length': '0'},
            match=[responses.matchers.header_matcher({"Range": "bytes=0-2"})]
        )

        asset_data = {
            'id': 'not_found.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': external_test_asset_url
        }

        # create the asset
        response = self.client.put(
            reverse_version('asset-detail', args=[collection.name, item.name, asset_data['id']]),
            data=asset_data,
            content_type="application/json"
        )

        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')
        self.assertIn(
            'Provided URL is unreachable',
            description['href'],
            msg=f'Unexpected field error {description}'
        )

    @responses.activate
    def test_create_asset_validate_external_url_bad_content(self):
        collection = self.collection
        item = self.item
        external_test_asset_url = 'https://example.com/api/123.jpeg'
        collection.allow_external_assets = True
        collection.external_asset_whitelist = ['https://example.com']
        collection.save()

        # Mock response of external asset url returning wrong content length
        responses.add(
            method=responses.GET,
            url=external_test_asset_url,
            body='',
            status=200,
            content_type='application/json',
            adding_headers={'Content-Length': '0'},
            match=[responses.matchers.header_matcher({"Range": "bytes=0-2"})]
        )

        asset_data = {
            'id': 'not_found.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': external_test_asset_url
        }

        # create the asset
        response = self.client.put(
            reverse_version('asset-detail', args=[collection.name, item.name, asset_data['id']]),
            data=asset_data,
            content_type="application/json"
        )

        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')
        self.assertIn(
            'Provided URL returns bad content',
            description['href'],
            msg=f'Unexpected field error {description}'
        )

    def test_update_asset_with_external_url(self):
        collection = self.collection
        item = self.item

        collection.allow_external_assets = True
        collection.external_asset_whitelist = [settings.EXTERNAL_TEST_ASSET_URL]
        collection.save()

        asset = self.factory.create_asset_sample(item=self.item, sample='asset-1', db_create=True)

        asset_data = asset.get_json('put')
        asset_data['href'] = settings.EXTERNAL_TEST_ASSET_URL

        response = self.client.put(
            reverse_version('asset-detail', args=[collection.name, item.name, asset.attr_name]),
            data=asset_data,
            content_type='application/json'
        )

        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(json_data['href'], asset_data['href'])

        updated_asset = Asset.objects.last()
        self.assertEqual(updated_asset.file, asset_data['href'])
        self.assertTrue(updated_asset.is_external)
        self.assertTrue(updated_asset.file_size, -1)

    def test_get_asset_with_external_url(self):
        collection = self.collection
        item = self.item

        asset = self.factory.create_asset_sample(
            item=self.item, sample='external-asset', db_create=True
        )

        response = self.client.get(
            reverse_version('asset-detail', args=[collection.name, item.name, asset.attr_name])
        )

        json_data = response.json()

        self.assertEqual(json_data['href'], asset.attr_file)

    def test_create_asset_with_invalid_external_url(self):
        collection = self.collection
        item = self.item

        collection.allow_external_assets = True
        collection.save()

        asset_data = {
            'id': 'clouds.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': 'this-is-not-a-url'
        }

        # create the asset
        response = self.client.put(
            reverse_version('asset-detail', args=[collection.name, item.name, asset_data['id']]),
            data=asset_data,
            content_type="application/json"
        )

        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')

        self.assertEqual(
            "Invalid URL provided", description['href'][0], msg="Unexpected error message"
        )

    def test_create_asset_with_inexistent_external_url(self):
        collection = self.collection
        item = self.item

        collection.allow_external_assets = True
        collection.external_asset_whitelist = [
            settings.EXTERNAL_TEST_ASSET_URL, 'https://map.geo.admin.ch'
        ]
        collection.save()

        asset_data = {
            'id': 'clouds.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': settings.EXTERNAL_TEST_ASSET_URL
        }

        # create the asset with an existing one
        response = self.client.put(
            reverse_version('asset-detail', args=[collection.name, item.name, asset_data['id']]),
            data=asset_data,
            content_type="application/json"
        )

        self.assertStatusCode(201, response)

        asset_data['href'] = 'https://map.geo.admin.ch/notexist.jpg'
        # create the asset with an existing one
        response = self.client.put(
            reverse_version('asset-detail', args=[collection.name, item.name, asset_data['id']]),
            data=asset_data,
            content_type="application/json"
        )

        description = response.json()['description']

        self.assertIn('href', description, msg=f'Unexpected field error {description}')

        self.assertEqual(
            "Provided URL is unreachable", description['href'][0], msg="Unexpected error message"
        )

    def test_create_asset_with_inexistent_domain(self):
        collection = self.collection
        item = self.item

        collection.allow_external_assets = True
        collection.external_asset_whitelist = ['https://swiss']
        collection.save()

        asset_data = {
            'id': 'clouds.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': settings.EXTERNAL_TEST_ASSET_URL
        }

        asset_data['href'] = 'https://swisssssssstopo.ch/inexistent.jpg'
        # create the asset with an existing one
        response = self.client.put(
            reverse_version('asset-detail', args=[collection.name, item.name, asset_data['id']]),
            data=asset_data,
            content_type="application/json"
        )

        description = response.json()['description']

        self.assertIn('href', description, msg=f'Unexpected field error {description}')

        self.assertEqual(
            "Provided URL is unreachable", description['href'][0], msg="Unexpected error message"
        )

    def test_delete_asset_with_external_url(self):
        collection = self.collection
        item = self.item

        asset = self.factory.create_asset_sample(
            item=self.item, sample='external-asset', db_create=True
        )

        response = self.client.delete(
            reverse_version('asset-detail', args=[collection.name, item.name, asset.attr_name])
        )

        self.assertStatusCode(200, response)
