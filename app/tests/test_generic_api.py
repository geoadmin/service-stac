import logging
from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.test import Client
from django.test import override_settings

from stac_api.utils import get_link

from tests.base_test import StacBaseTestCase
from tests.data_factory import Factory
from tests.utils import client_login
from tests.utils import get_http_error_description
from tests.utils import mock_s3_asset_file

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
        Factory().create_collection_samples(3, db_create=True)

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

    @mock_s3_asset_file
    def setUp(self):
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample(
            name='collection-1',
            db_create=True,
        )
        self.item = self.factory.create_item_sample(
            collection=self.collection.model,
            name='item-1',
            db_create=True,
        )
        self.asset = self.factory.create_asset_sample(
            item=self.item.model,
            name='asset-1',
            db_create=True,
        )

    def test_get_precondition(self):
        for endpoint in [
            f'collections/{self.collection["name"]}',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}'
            f'/assets/{self.asset["name"]}'
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

    def test_put_precondition(self):
        client_login(self.client)
        for (endpoint, sample) in [
            (
                f'collections/{self.collection["name"]}',
                self.factory.create_collection_sample(
                    name=self.collection["name"],
                    sample='collection-2',
                )
            ),
            (
                f'collections/{self.collection["name"]}/items/{self.item["name"]}',
                self.factory.create_item_sample(
                    collection=self.collection.model,
                    name=self.item["name"],
                    sample='item-2',
                )
            ),
            (
                f'collections/{self.collection["name"]}/items/{self.item["name"]}'
                f'/assets/{self.asset["name"]}',
                self.factory.create_asset_sample(
                    item=self.item.model,
                    name=self.asset["name"],
                    sample='asset-1-updated',
                    checksum_multihash=self.asset.model.checksum_multihash
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

                response = self.client.put(
                    f"/{API_BASE}/{endpoint}",
                    sample.get_json('put'),
                    content_type="application/json",
                    HTTP_IF_MATCH='"abc"'
                )
                self.assertStatusCode(412, response)

                response = self.client.put(
                    f"/{API_BASE}/{endpoint}",
                    sample.get_json('put'),
                    content_type="application/json",
                    HTTP_IF_MATCH=etag1
                )
                self.assertStatusCode(200, response)

    def test_patch_precondition(self):
        client_login(self.client)
        for (endpoint, data) in [
            (
                f'collections/{self.collection["name"]}',
                {
                    'title': 'New title patched'
                },
            ),
            (
                f'collections/{self.collection["name"]}/items/{self.item["name"]}',
                {
                    'properties': {
                        'title': 'New title patched'
                    }
                },
            ),
            (
                f'collections/{self.collection["name"]}/items/{self.item["name"]}'
                f'/assets/{self.asset["name"]}',
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
            f'collections/{self.collection["name"]}/items/{self.item["name"]}'
            f'/assets/{self.asset["name"]}',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}',
            # f'collections/{self.collection["name"]}',
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


class ApiCacheHeaderTestCase(StacBaseTestCase):

    @classmethod
    @mock_s3_asset_file
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample(
            name='collection-1',
            db_create=True,
        )
        cls.item = cls.factory.create_item_sample(
            collection=cls.collection.model,
            name='item-1',
            db_create=True,
        )
        cls.asset = cls.factory.create_asset_sample(
            item=cls.item.model,
            name='asset-1',
            db_create=True,
        )

    @override_settings(CACHE_MIDDLEWARE_SECONDS=3600)
    def test_get_cache_header(self):
        for endpoint in [
            '',  # landing page
            'conformance',
            'search',
            'search?ids=item-1',
            f'collections/{self.collection["name"]}',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}'
            f'/assets/{self.asset["name"]}'
        ]:
            with self.subTest(endpoint=endpoint):
                now = datetime.now()
                response = self.client.get(f"/{API_BASE}/{endpoint}")
                self.assertStatusCode(200, response)

                self.assertTrue(
                    response.has_header('Cache-Control'), msg="Cache-Control header missing"
                )
                self.assertEqual(
                    response['Cache-Control'],
                    'max-age=3600, public',
                    msg='Wrong cache-control values'
                )

                self.assertTrue(response.has_header('Expires'), msg="Expires header missing")

                expires = datetime.strptime(response['Expires'], '%a, %d %b %Y %H:%M:%S GMT')
                self.assertAlmostEqual((expires - now).total_seconds(),
                                       timedelta(seconds=3600).total_seconds(),
                                       delta=2)

    @override_settings(CACHE_MIDDLEWARE_SECONDS=3600)
    def test_head_cache_header(self):
        for endpoint in [
            '',  # landing page
            'conformance',
            'search',
            'search?ids=item-1',
            f'collections/{self.collection["name"]}',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}'
            f'/assets/{self.asset["name"]}'
        ]:
            with self.subTest(endpoint=endpoint):
                now = datetime.now()
                response = self.client.head(f"/{API_BASE}/{endpoint}")
                self.assertStatusCode(200, response)

                self.assertTrue(
                    response.has_header('Cache-Control'), msg="Cache-Control header missing"
                )
                self.assertEqual(
                    response['Cache-Control'],
                    'max-age=3600, public',
                    msg='Wrong cache-control values'
                )

                self.assertTrue(response.has_header('Expires'), msg="Expires header missing")

                expires = datetime.strptime(response['Expires'], '%a, %d %b %Y %H:%M:%S GMT')
                self.assertAlmostEqual((expires - now).total_seconds(),
                                       timedelta(seconds=3600).total_seconds(),
                                       delta=2)
