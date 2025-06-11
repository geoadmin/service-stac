import logging

import responses

from django.conf import settings
from django.test import Client
from django.test import override_settings

from stac_api.models.collection import CollectionAsset

from tests.tests_10.base_test import TEST_SERVER
from tests.tests_10.base_test import StacBaseTestCase
from tests.tests_10.data_factory import Factory
from tests.tests_10.utils import reverse_version
from tests.utils import MockS3PerTestMixin
from tests.utils import get_auth_headers

logger = logging.getLogger(__name__)


@override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
class CollectionAssetsExternalAssetEndpointTestCase(MockS3PerTestMixin, StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        super().setUp()
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.client = Client(headers=get_auth_headers())
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_create_collection_asset_with_external_url(self):
        collection = self.collection
        collection_asset_data = {
            'id': 'clouds.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': settings.EXTERNAL_TEST_ASSET_URL
        }

        # create the asset, which isn't allowed
        response = self.client.put(
            reverse_version(
                'collection-asset-detail', args=[collection.name, collection_asset_data['id']]
            ),
            data=collection_asset_data,
            content_type="application/json"
        )

        logger.debug("response external %s", response.json())
        self.assertStatusCode(400, response)
        self.assertIn('href', response.json()['description'])
        self.assertIn('Found read-only property in payload', response.json()['description']['href'])

        collection.allow_external_assets = True
        collection.external_asset_whitelist = [settings.EXTERNAL_TEST_ASSET_URL]
        collection.save()

        # create the asset, now it's allowed
        response = self.client.put(
            reverse_version(
                'collection-asset-detail', args=[collection.name, collection_asset_data['id']]
            ),
            data=collection_asset_data,
            content_type="application/json"
        )

        json_data = response.json()
        self.assertStatusCode(201, response)
        self.assertEqual(json_data['href'], collection_asset_data['href'])

        new_collection_asset = CollectionAsset.objects.last()
        self.assertEqual(new_collection_asset.file, collection_asset_data['href'])
        self.assertTrue(new_collection_asset.is_external)
        logger.debug("created asset file size %s", new_collection_asset.file_size)
        self.assertEqual(new_collection_asset.file_size, 0)

    @responses.activate
    def test_create_collection_asset_validate_external_url(self):
        collection = self.collection
        external_test_asset_url = 'https://example.com/api/123.jpeg'
        collection.allow_external_assets = True
        collection.external_asset_whitelist = ['https://example.com']
        collection.save()

        # Mock response of external asset url
        # This is to ensure the URL appears as though it is reachable
        # Otherwise the asset cannot be created
        responses.add(
            method=responses.GET,
            url=external_test_asset_url,
            body='som',
            status=200,
            content_type='application/json',
            adding_headers={'Content-Length': '3'},
            match=[responses.matchers.header_matcher({"Range": "bytes=0-2"})]
        )

        collection_asset_data = {
            'id': 'clouds.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',
            'href': external_test_asset_url
        }

        # create the asset
        response = self.client.put(
            reverse_version(
                'collection-asset-detail', args=[collection.name, collection_asset_data['id']]
            ),
            data=collection_asset_data,
            content_type="application/json"
        )

        json_data = response.json()
        self.assertStatusCode(201, response)
        self.assertEqual(json_data['href'], collection_asset_data['href'])

        new_collection_asset = CollectionAsset.objects.last()
        self.assertEqual(new_collection_asset.file, collection_asset_data['href'])
        self.assertTrue(new_collection_asset.is_external)
        self.assertEqual(new_collection_asset.file_size, 0)

    @responses.activate
    def test_create_collection_asset_validate_external_url_not_found(self):
        collection = self.collection
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

        collection_asset_data = {
            'id': 'not_found.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': external_test_asset_url
        }

        # create the asset
        response = self.client.put(
            reverse_version(
                'collection-asset-detail', args=[collection.name, collection_asset_data['id']]
            ),
            data=collection_asset_data,
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

        last_collection_asset = CollectionAsset.objects.last()
        self.assertIsNone(last_collection_asset)  #should be none as no new asset was created

    @responses.activate
    def test_create_collection_asset_validate_external_url_bad_content(self):
        collection = self.collection
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

        collection_asset_data = {
            'id': 'not_found.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': external_test_asset_url
        }

        # create the asset
        response = self.client.put(
            reverse_version(
                'collection-asset-detail', args=[collection.name, collection_asset_data['id']]
            ),
            data=collection_asset_data,
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

        last_collection_asset = CollectionAsset.objects.last()
        self.assertIsNone(last_collection_asset)

    def test_update_collection_asset_with_external_url(self):
        collection = self.collection

        collection.allow_external_assets = True
        collection.external_asset_whitelist = [settings.EXTERNAL_TEST_ASSET_URL]
        collection.save()

        asset = self.factory.create_collection_asset_sample(
            collection=collection, sample='asset-1', db_create=True
        )

        collection_asset_data = asset.get_json('put')
        collection_asset_data['href'] = settings.EXTERNAL_TEST_ASSET_URL

        response = self.client.put(
            reverse_version('collection-asset-detail', args=[collection.name, asset.attr_name]),
            data=collection_asset_data,
            content_type='application/json'
        )

        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(json_data['href'], collection_asset_data['href'])

        updated_collection_asset = CollectionAsset.objects.last()
        self.assertEqual(updated_collection_asset.file, collection_asset_data['href'])
        self.assertTrue(updated_collection_asset.is_external)
        self.assertTrue(updated_collection_asset.file_size, -1)

    def test_get_collection_asset_with_external_url(self):
        collection = self.collection

        collection_asset = self.factory.create_collection_asset_sample(
            collection=collection, sample='external-asset', db_create=True
        )

        response = self.client.get(
            reverse_version(
                'collection-asset-detail', args=[collection.name, collection_asset.attr_name]
            )
        )

        json_data = response.json()

        self.assertEqual(json_data['href'], f"{TEST_SERVER}/{collection_asset.attr_file}")

    def test_create_collection_asset_with_invalid_external_url(self):
        collection = self.collection

        collection.allow_external_assets = True
        collection.save()

        collection_asset_data = {
            'id': 'clouds.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': 'this-is-not-a-url'
        }

        # create the asset
        response = self.client.put(
            reverse_version(
                'collection-asset-detail', args=[collection.name, collection_asset_data['id']]
            ),
            data=collection_asset_data,
            content_type="application/json"
        )

        self.assertStatusCode(400, response)
        description = response.json()['description']
        self.assertIn('href', description, msg=f'Unexpected field error {description}')

        self.assertEqual(
            "Invalid URL provided", description['href'][0], msg="Unexpected error message"
        )

        last_collection_asset = CollectionAsset.objects.last()
        self.assertIsNone(last_collection_asset)

    def test_create_collection_asset_with_inexistent_external_url(self):
        collection = self.collection

        collection.allow_external_assets = True
        collection.external_asset_whitelist = [
            settings.EXTERNAL_TEST_ASSET_URL, 'https://map.geo.admin.ch'
        ]
        collection.save()

        collection_asset_data = {
            'id': 'clouds.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': settings.EXTERNAL_TEST_ASSET_URL
        }

        # create the asset with an existing one
        response = self.client.put(
            reverse_version(
                'collection-asset-detail', args=[collection.name, collection_asset_data['id']]
            ),
            data=collection_asset_data,
            content_type="application/json"
        )

        self.assertStatusCode(201, response)

        collection_asset_data['href'] = 'https://map.geo.admin.ch/notexist.jpg'
        # create the asset with an existing one
        response = self.client.put(
            reverse_version(
                'collection-asset-detail', args=[collection.name, collection_asset_data['id']]
            ),
            data=collection_asset_data,
            content_type="application/json"
        )

        self.assertStatusCode(400, response)

        description = response.json()['description']

        self.assertIn('href', description, msg=f'Unexpected field error {description}')

        self.assertEqual(
            "Provided URL is unreachable", description['href'][0], msg="Unexpected error message"
        )

        last_collection_asset = CollectionAsset.objects.last()
        self.assertNotEqual(last_collection_asset.file, collection_asset_data['href'])

    def test_create_collection_asset_with_inexistent_domain(self):
        collection = self.collection

        collection.allow_external_assets = True
        collection.external_asset_whitelist = ['https://swiss']
        collection.save()

        collection_asset_data = {
            'id': 'clouds.jpg',
            'description': 'High in the sky',
            'type': 'image/jpeg',  # specify the file explicitly
            'href': settings.EXTERNAL_TEST_ASSET_URL
        }

        collection_asset_data['href'] = 'https://swisssssssstopo.ch/inexistent.jpg'
        # create the asset with an existing one
        response = self.client.put(
            reverse_version(
                'collection-asset-detail', args=[collection.name, collection_asset_data['id']]
            ),
            data=collection_asset_data,
            content_type="application/json"
        )

        self.assertStatusCode(400, response)

        description = response.json()['description']

        self.assertIn('href', description, msg=f'Unexpected field error {description}')

        self.assertEqual(
            "Provided URL is unreachable", description['href'][0], msg="Unexpected error message"
        )

        last_collection_asset = CollectionAsset.objects.last()
        self.assertIsNone(last_collection_asset)

    def test_delete_collection_asset_with_external_url(self):
        collection = self.collection

        collection_asset = self.factory.create_collection_asset_sample(
            collection=collection, sample='external-asset', db_create=True
        )

        new_collection_asset = CollectionAsset.objects.last()
        self.assertEqual(new_collection_asset.file, settings.EXTERNAL_TEST_ASSET_URL)

        response = self.client.delete(
            reverse_version(
                'collection-asset-detail', args=[collection.name, collection_asset.attr_name]
            )
        )

        self.assertStatusCode(200, response)

        last_collection_asset = CollectionAsset.objects.last()
        self.assertIsNone(last_collection_asset)
