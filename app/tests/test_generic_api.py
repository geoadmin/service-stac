import logging
from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.test import Client
from django.test import override_settings

from stac_api.models import AssetUpload
from stac_api.utils import get_link
from stac_api.utils import get_sha256_multihash
from stac_api.utils import utc_aware

from tests.base_test import StacBaseTestCase
from tests.data_factory import Factory
from tests.utils import client_login
from tests.utils import disableLogger
from tests.utils import get_http_error_description
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)

STAC_BASE_V = settings.STAC_BASE_V


class ApiGenericTestCase(StacBaseTestCase):

    def setUp(self):
        self.client = Client()

    def test_http_error_collection_not_found(self):
        response = self.client.get(f"/{STAC_BASE_V}/collections/not-found")
        self.assertStatusCode(404, response)

    def test_http_error_500_exception(self):
        with self.settings(DEBUG_PROPAGATE_API_EXCEPTIONS=True), disableLogger('stac_api.apps'):
            response = self.client.get("/tests/test_http_500")
            self.assertStatusCode(500, response)
            self.assertEqual(response.json()['description'], "AttributeError('test exception')")


class ApiPaginationTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collections = cls.factory.create_collection_samples(3, db_create=True)

    def setUp(self):
        self.client = Client()
        self.maxDiff = None  # pylint: disable=invalid-name

    def _get_check_link(self, links, rel, endpoint):
        link = get_link(links, rel)
        self.assertIsNotNone(link, msg=f'Pagination {rel} link missing')
        self.assertTrue(isinstance(link['href'], str), msg='href is not a string')
        self.assertTrue(
            link['href'].startswith(f'http://testserver/api/stac/v0.9/{endpoint}?cursor='),
            msg='Invalid href link pagination string'
        )
        return link

    def _read_link(self, link, rel, other_pages, result_attribute):
        # Read the link page
        response = self.client.get(link['href'].replace('http://testserver', ''))
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))

        # Make sure next page is different from others
        for page in other_pages:
            self.assertNotEqual(
                page[result_attribute],
                json_data[result_attribute],
                msg=f"{rel} page is not different from initial"
            )
        return json_data

    def test_invalid_limit_query(self):
        items = self.factory.create_item_samples(3, self.collections[0].model, db_create=True)
        for endpoint in ['collections', f'collections/{self.collections[0]["name"]}/items']:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(f"/{STAC_BASE_V}/{endpoint}?limit=0")
                self.assertStatusCode(400, response)
                self.assertEqual(['limit query parameter too small, must be in range 1..100'],
                                 response.json()['description'],
                                 msg='Unexpected error message')

                response = self.client.get(f"/{STAC_BASE_V}/{endpoint}?limit=test")
                self.assertStatusCode(400, response)
                self.assertEqual(['Invalid limit query parameter: must be an integer'],
                                 response.json()['description'],
                                 msg='Unexpected error message')

                response = self.client.get(f"/{STAC_BASE_V}/{endpoint}?limit=-1")
                self.assertStatusCode(400, response)
                self.assertEqual(['limit query parameter too small, must be in range 1..100'],
                                 response.json()['description'],
                                 msg='Unexpected error message')

                response = self.client.get(f"/{STAC_BASE_V}/{endpoint}?limit=1000")
                self.assertStatusCode(400, response)
                self.assertEqual(['limit query parameter too big, must be in range 1..100'],
                                 response.json()['description'],
                                 msg='Unexpected error message')

    @mock_s3_asset_file
    def test_pagination(self):
        # pylint: disable=too-many-locals
        items = self.factory.create_item_samples(3, self.collections[0].model, db_create=True)
        asset = self.factory.create_asset_sample(items[0].model, db_create=True)
        for i in range(1, 4):
            AssetUpload.objects.create(
                asset=asset.model,
                upload_id=f'upload-{i}',
                status=AssetUpload.Status.ABORTED,
                checksum_multihash=get_sha256_multihash(b'upload-%d' % i),
                number_parts=2,
                ended=utc_aware(datetime.utcnow()),
                md5_parts=['md5-%d-1' % i, 'md5-%d-2' % i]
            )
        for endpoint, result_attribute in [
            ('collections', 'collections'),
            (f'collections/{self.collections[0]["name"]}/items', 'features'),
            (f'collections/{self.collections[0]["name"]}/items/{items[0]["name"]}/'
             f'assets/{asset["name"]}/uploads', 'uploads')
        ]:
            with self.subTest(endpoint=endpoint):
                # Page 1:
                response = self.client.get(f"/{STAC_BASE_V}/{endpoint}?limit=1")
                self.assertStatusCode(200, response)
                page_1 = response.json()

                # Make sure previous link is not present
                self.assertIsNone(
                    get_link(page_1['links'], 'previous'),
                    msg='Pagination previous link present for initial query'
                )

                # Get and check next link
                next_link_2 = self._get_check_link(page_1['links'], 'next', endpoint)

                # PAGE 2:
                # Read the next page
                page_2 = self._read_link(next_link_2, 'next', [page_1], result_attribute)

                # get and check next link
                next_link_3 = self._get_check_link(page_2['links'], 'next', endpoint)

                # Get and check previous link
                previous_link_1 = self._get_check_link(page_2['links'], 'previous', endpoint)

                # PAGE 3:
                # Read the next page
                page_3 = self._read_link(next_link_3, 'next', [page_1, page_2], result_attribute)

                # Make sure next link is not present
                self.assertIsNone(
                    get_link(page_3['links'], 'next'),
                    msg='Pagination next link present for last page'
                )

                # Get and check previous link
                previous_link_2 = self._get_check_link(page_3['links'], 'previous', endpoint)

                # Navigate back with previous links
                # PAGE: 2
                _page_2 = self._read_link(
                    previous_link_2, 'previous', [page_1, page_3], result_attribute
                )

                self.assertEqual(
                    page_2[result_attribute],
                    _page_2[result_attribute],
                    msg="Previous link for page 2 is not equal to next link to page 2"
                )

                # get and check next link
                _next_link_3 = self._get_check_link(_page_2['links'], 'next', endpoint)

                # Get and check previous link
                _previous_link_1 = self._get_check_link(_page_2['links'], 'previous', endpoint)

                # PAGE 1:
                _page_1 = self._read_link(
                    _previous_link_1, 'previous', [_page_2, page_2, page_3], result_attribute
                )
                self.assertEqual(
                    page_1[result_attribute],
                    _page_1[result_attribute],
                    msg="Previous link for page 1 is not equal to initial page 1"
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
            name='asset-1.tiff',
            db_create=True,
        )

    def get_etag(self, endpoint):
        # Get first the ETag
        _response = self.client.get(f"/{STAC_BASE_V}/{endpoint}")
        self.assertStatusCode(200, _response)
        # The ETag change between each test call due to the created,
        # updated time that are in the hash computation of the ETag
        self.check_header_etag(None, _response)
        return _response['ETag']

    def test_get_precondition(self):
        for endpoint in [
            f'collections/{self.collection["name"]}',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}'
            f'/assets/{self.asset["name"]}'
        ]:
            with self.subTest(endpoint=endpoint):
                response1 = self.client.get(f"/{STAC_BASE_V}/{endpoint}")
                self.assertStatusCode(200, response1)
                # The ETag change between each test call due to the created, updated time that are
                # in the hash computation of the ETag
                self.check_header_etag(None, response1)

                response2 = self.client.get(
                    f"/{STAC_BASE_V}/{endpoint}", HTTP_IF_NONE_MATCH=response1['ETag']
                )
                self.assertEqual(response1['ETag'], response2['ETag'])
                self.assertStatusCode(304, response2)

                response3 = self.client.get(
                    f"/{STAC_BASE_V}/{endpoint}", HTTP_IF_MATCH=response1['ETag']
                )
                self.assertEqual(response1['ETag'], response3['ETag'])
                self.assertStatusCode(200, response3)

                response4 = self.client.get(f"/{STAC_BASE_V}/{endpoint}", HTTP_IF_MATCH='"abcd"')
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
                    media_type=self.asset['media_type'],
                    checksum_multihash=self.asset["checksum_multihash"]
                )
            ),
        ]:
            with self.subTest(endpoint=endpoint):

                response = self.client.put(
                    f"/{STAC_BASE_V}/{endpoint}",
                    sample.get_json('put'),
                    content_type="application/json",
                    HTTP_IF_MATCH='"abc"'
                )
                self.assertStatusCode(412, response)

                response = self.client.put(
                    f"/{STAC_BASE_V}/{endpoint}",
                    sample.get_json('put'),
                    content_type="application/json",
                    HTTP_IF_MATCH=self.get_etag(endpoint)
                )
                self.assertStatusCode(200, response)

    def test_wrong_media_type(self):
        client_login(self.client)

        for (request_methods, endpoint, data) in [
            (
                ['put', 'patch'],
                f'collections/{self.collection["name"]}',
                {},
            ),
            (
                ['put', 'patch'],
                f'collections/{self.collection["name"]}/items/{self.item["name"]}',
                {},
            ),
            (['post'], 'search', {
                "query": {
                    "title": {
                        "eq": "My item 1"
                    }
                }
            }),
        ]:
            with self.subTest(endpoint=endpoint):
                client_requests = [getattr(self.client, method) for method in request_methods]
                for client_request in client_requests:
                    response = client_request(
                        f"/{STAC_BASE_V}/{endpoint}", data=data, content_type="plain/text"
                    )
                    self.assertStatusCode(415, response)

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

                response = self.client.patch(
                    f"/{STAC_BASE_V}/{endpoint}",
                    data,
                    content_type="application/json",
                    HTTP_IF_MATCH='"abc"'
                )
                self.assertStatusCode(412, response)

                response = self.client.patch(
                    f"/{STAC_BASE_V}/{endpoint}",
                    data,
                    content_type="application/json",
                    HTTP_IF_MATCH=self.get_etag(endpoint)
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
                etag1 = self.get_etag(endpoint)

                response = self.client.delete(
                    f"/{STAC_BASE_V}/{endpoint}",
                    content_type="application/json",
                    HTTP_IF_MATCH='"abc"'
                )
                self.assertStatusCode(
                    412, response, msg='Request should be refused due to precondition failed'
                )

                response = self.client.delete(
                    f"/{STAC_BASE_V}/{endpoint}",
                    content_type="application/json",
                    HTTP_IF_MATCH=etag1
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
                response = self.client.get(f"/{STAC_BASE_V}/{endpoint}")
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
                response = self.client.head(f"/{STAC_BASE_V}/{endpoint}")
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


class ApiCORSHeaderTestCase(StacBaseTestCase):

    @classmethod
    @mock_s3_asset_file
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample(db_create=True,)
        cls.item = cls.factory.create_item_sample(
            collection=cls.collection.model,
            db_create=True,
        )
        cls.asset = cls.factory.create_asset_sample(
            item=cls.item.model,
            db_create=True,
        )

    def test_get_cors_header(self):
        for endpoint in [
            '',  # landing page
            'conformance',
            'collections',
            f'collections/{self.collection["name"]}',
            f'collections/{self.collection["name"]}/items',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}'
            f'/assets',
            f'collections/{self.collection["name"]}/items/{self.item["name"]}'
            f'/assets/{self.asset["name"]}'
        ]:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(f"/{STAC_BASE_V}/{endpoint}")
                self.assertStatusCode(200, response)

                self.assertTrue(
                    response.has_header('Access-Control-Allow-Origin'),
                    msg="CORS header allow-origin missing"
                )
                self.assertEqual(
                    response['Access-Control-Allow-Origin'],
                    '*',
                    msg='Wrong CORS allow-origin value'
                )

                self.assertTrue(
                    response.has_header('Access-Control-Allow-Methods'),
                    msg="CORS header allow-methods missing"
                )

                self.assertEqual(
                    response['Access-Control-Allow-Methods'],
                    'GET,HEAD',
                    msg='Wrong CORS allow-methods value'
                )

                self.assertTrue(
                    response.has_header('Access-Control-Allow-Headers'),
                    msg="CORS header allow-Headers missing"
                )

                self.assertEqual(
                    response['Access-Control-Allow-Headers'],
                    'Content-Type,Accept',
                    msg='Wrong CORS allow-Headers value'
                )

    def test_get_cors_header_search(self):
        response = self.client.get(f"/{STAC_BASE_V}/search")
        self.assertStatusCode(200, response)

        self.assertTrue(
            response.has_header('Access-Control-Allow-Origin'),
            msg="CORS header allow-origin missing"
        )

        self.assertEqual(
            response['Access-Control-Allow-Origin'], '*', msg='Wrong CORS allow-origin value'
        )

        self.assertTrue(
            response.has_header('Access-Control-Allow-Methods'),
            msg="CORS header allow-methods missing"
        )

        self.assertEqual(
            response['Access-Control-Allow-Methods'],
            'GET,HEAD,POST',
            msg='Wrong CORS allow-methods value'
        )

        self.assertTrue(
            response.has_header('Access-Control-Allow-Headers'),
            msg="CORS header allow-Headers missing"
        )

        self.assertEqual(
            response['Access-Control-Allow-Headers'],
            'Content-Type,Accept',
            msg='Wrong CORS allow-Headers value'
        )
