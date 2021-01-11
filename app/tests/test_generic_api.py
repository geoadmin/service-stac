import logging

import requests_mock

from django.conf import settings
from django.test import Client

from stac_api.utils import get_link

from tests.base_test import StacBaseTestCase
from tests.data_factory import AssetSample
from tests.data_factory import Factory
from tests.utils import client_login
from tests.utils import get_http_error_description
from tests.utils import mock_requests_asset_file
from tests.utils import mock_s3
from tests.utils import mock_s3_bucket

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


class ApiGenericTestCase(StacBaseTestCase):

    def setUp(self):
        self.client = Client()

    def test_http_error_collection_not_found(self):
        response = self.client.get(f"/{API_BASE}/collections/not-found")
        self.assertStatusCode(404, response)

    def test_http_error_500_exception(self):
        with self.settings(DEBUG_PROPAGATE_API_EXCEPTIONS=True):
            response = self.client.get("/tests/test_http_500")
            self.assertStatusCode(500, response)


class ApiPaginationTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        collections = Factory().create_collection_samples(3, db_create=True)

    def setUp(self):
        self.client = Client()

    def test_invalid_limit_query(self):
        response = self.client.get(f"/{API_BASE}/collections?limit=0")
        self.assertStatusCode(400, response)

        response = self.client.get(f"/{API_BASE}/collections?limit=test")
        self.assertStatusCode(400, response)

        response = self.client.get(f"/{API_BASE}/collections?limit=-1")
        self.assertStatusCode(400, response)

        response = self.client.get(f"/{API_BASE}/collections?limit=1000")
        self.assertStatusCode(400, response)

    def test_http_error_invalid_query_param(self):
        response = self.client.get(f"/{API_BASE}/collections?limit=0")
        self.assertStatusCode(400, response)

    def test_pagination(self):

        response = self.client.get(f"/{API_BASE}/collections?limit=1")
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))

        # Check next link
        next_link = get_link(json_data['links'], 'next')
        self.assertIsNotNone(next_link, msg='Pagination next link missing')
        self.assertTrue(isinstance(next_link['href'], str), msg='href is not a string')
        self.assertTrue(
            next_link['href'].startswith('http://testserver/api/stac/v0.9/collections?cursor='),
            msg='Invalid href link pagination string'
        )

        # Check previous link
        previous_link = get_link(json_data['links'], 'previous')
        self.assertIsNone(previous_link, msg='Pagination previous link present for initial query')

        # Get the next page
        response = self.client.get(next_link['href'].replace('http://testserver', ''))
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))

        # Check next link
        next_link = get_link(json_data['links'], 'next')
        self.assertIsNotNone(next_link, msg='Pagination next link missing')
        self.assertTrue(isinstance(next_link['href'], str), msg='href is not a string')
        self.assertTrue(
            next_link['href'].startswith('http://testserver/api/stac/v0.9/collections?cursor='),
            msg='Invalid href link pagination string'
        )

        # Check previous link
        previous_link = get_link(json_data['links'], 'previous')
        self.assertIsNotNone(previous_link, msg='Pagination previous link is missing')
        self.assertTrue(isinstance(previous_link['href'], str), msg='href is not a string')
        self.assertTrue(
            previous_link['href'].startswith('http://testserver/api/stac/v0.9/collections?cursor='),
            msg='Invalid href link pagination string'
        )

        # Get the next page
        response = self.client.get(next_link['href'].replace('http://testserver', ''))
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))

        # Check next link
        next_link = get_link(json_data['links'], 'next')
        self.assertIsNone(next_link, msg='Pagination next link is present')

        # Check previous link
        previous_link = get_link(json_data['links'], 'previous')
        self.assertIsNotNone(previous_link, msg='Pagination previous link is missing')
        self.assertTrue(isinstance(previous_link['href'], str), msg='href is not a string')
        self.assertTrue(
            previous_link['href'].startswith('http://testserver/api/stac/v0.9/collections?cursor='),
            msg='Invalid href link pagination string'
        )


class ApiETagPreconditionTestCase(StacBaseTestCase):

    @classmethod
    @mock_s3
    def setUpTestData(cls):
        mock_s3_bucket()
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample(name='collection-1').model
        cls.item = cls.factory.create_item_sample(collection=cls.collection, name='item-1').model
        cls.asset = cls.factory.create_asset_sample(item=cls.item, name='asset-1').model

    def test_get_precondition(self):
        for endpoint in [
            'collections/collection-1',
            'collections/collection-1/items/item-1',
            'collections/collection-1/items/item-1/assets/asset-1'
        ]:
            with self.subTest(endpoint=endpoint):
                response1 = self.client.get(f"/{API_BASE}/{endpoint}")
                self.assertStatusCode(200, response1)
                # The ETag change between each test call due to the created, updated time that are
                # in the hash computation of the ETag
                self.check_header_etag(None, response1)

                response2 = self.client.get(
                    f"/{API_BASE}/{endpoint}", HTTP_IF_NONE_MATCH=response1['ETag']
                )
                self.assertEqual(response1['ETag'], response2['ETag'])
                self.assertStatusCode(304, response2)

                response3 = self.client.get(
                    f"/{API_BASE}/{endpoint}", HTTP_IF_MATCH=response1['ETag']
                )
                self.assertEqual(response1['ETag'], response3['ETag'])
                self.assertStatusCode(200, response3)

                response4 = self.client.get(f"/{API_BASE}/{endpoint}", HTTP_IF_MATCH='"abcd"')
                self.assertStatusCode(412, response4)

    @requests_mock.Mocker(kw='requests_mocker')
    def test_put_precondition(self, requests_mocker):
        client_login(self.client)
        for (endpoint, sample) in [
            (
                'collections/collection-1',
                self.factory.create_collection_sample(
                    name=self.collection.name, sample='collection-2'
                )
            ),
            (
                'collections/collection-1/items/item-1',
                self.factory.create_item_sample(
                    collection=self.collection, name=self.item.name, sample='item-2'
                )
            ),
            (
                'collections/collection-1/items/item-1/assets/asset-1',
                self.factory.create_asset_sample(
                    item=self.item,
                    name=self.asset.name,
                    sample='asset-1-updated',
                    checksum_multihash=self.asset.checksum_multihash
                )
            ),
        ]:
            with self.subTest(endpoint=endpoint):
                # Get first the ETag
                response = self.client.get(f"/{API_BASE}/{endpoint}")
                self.assertStatusCode(200, response)
                # The ETag change between each test call due to the created, updated time that are
                # in the hash computation of the ETag
                self.check_header_etag(None, response)
                etag1 = response['ETag']

                if isinstance(sample, AssetSample):
                    mock_requests_asset_file(requests_mocker, sample)

                response = self.client.put(
                    f"/{API_BASE}/{endpoint}",
                    sample.json,
                    content_type="application/json",
                    HTTP_IF_MATCH='"abc"'
                )
                self.assertStatusCode(412, response)

                response = self.client.put(
                    f"/{API_BASE}/{endpoint}",
                    sample.json,
                    content_type="application/json",
                    HTTP_IF_MATCH=etag1
                )
                self.assertStatusCode(200, response)

    def test_patch_precondition(self):
        client_login(self.client)
        for (endpoint, data) in [
            (
                'collections/collection-1',
                {
                    'title': 'New title patched'
                },
            ),
            (
                'collections/collection-1/items/item-1',
                {
                    'properties': {
                        'title': 'New title patched'
                    }
                },
            ),
            (
                'collections/collection-1/items/item-1/assets/asset-1',
                {
                    'title': 'New title patched'
                },
            ),
        ]:
            with self.subTest(endpoint=endpoint):
                # Get first the ETag
                response = self.client.get(f"/{API_BASE}/{endpoint}")
                self.assertStatusCode(200, response)
                # The ETag change between each test call due to the created, updated time that are
                # in the hash computation of the ETag
                self.check_header_etag(None, response)
                etag1 = response['ETag']

                response = self.client.patch(
                    f"/{API_BASE}/{endpoint}",
                    data,
                    content_type="application/json",
                    HTTP_IF_MATCH='"abc"'
                )
                self.assertStatusCode(412, response)

                response = self.client.patch(
                    f"/{API_BASE}/{endpoint}",
                    data,
                    content_type="application/json",
                    HTTP_IF_MATCH=etag1
                )
                self.assertStatusCode(200, response)

    def test_delete_precondition(self):
        client_login(self.client)
        for endpoint in [
            'collections/collection-1/items/item-1/assets/asset-1',
            'collections/collection-1/items/item-1',  # 'collections/collection-1',
        ]:
            with self.subTest(endpoint=endpoint):
                # Get first the ETag
                response = self.client.get(f"/{API_BASE}/{endpoint}")
                self.assertStatusCode(200, response)
                # The ETag change between each test call due to the created, updated time that are
                # in the hash computation of the ETag
                self.check_header_etag(None, response)
                etag1 = response['ETag']

                response = self.client.delete(
                    f"/{API_BASE}/{endpoint}",
                    content_type="application/json",
                    HTTP_IF_MATCH='"abc"'
                )
                self.assertStatusCode(
                    412, response, msg='Request should be refused due to precondition failed'
                )

                response = self.client.delete(
                    f"/{API_BASE}/{endpoint}", content_type="application/json", HTTP_IF_MATCH=etag1
                )
                self.assertStatusCode(200, response)
