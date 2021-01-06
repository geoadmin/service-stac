import logging

from django.conf import settings
from django.contrib.auth import get_user_model

from stac_api.utils import get_link

import tests.database as db
from tests.base_test import StacBaseTestCase
from tests.utils import get_http_error_description

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE
TEST_VALID_GEOMETRY = {
    "coordinates": [[
        [11.199955188064508, 45.30427347827474],
        [5.435800505341752, 45.34985402081985],
        [5.327213305905472, 48.19113734655604],
        [11.403439825339375, 48.14311756174606],
        [11.199955188064508, 45.30427347827474],
    ]],
    "type": "Polygon"
}


class ApiGenericTestCase(StacBaseTestCase):

    def setUp(self):
        self.username = 'SherlockHolmes'
        self.password = '221B_BakerStreet'
        self.superuser = get_user_model().objects.create_superuser(
            self.username, 'test_e_mail1234@some_fantasy_domainname.com', self.password
        )

    def test_invalid_limit_query(self):
        response = self.client.get(f"/{API_BASE}/collections?limit=0")
        self.assertEqual(400, response.status_code)

        response = self.client.get(f"/{API_BASE}/collections?limit=test")
        self.assertEqual(400, response.status_code)

        response = self.client.get(f"/{API_BASE}/collections?limit=-1")
        self.assertEqual(400, response.status_code)

        response = self.client.get(f"/{API_BASE}/collections?limit=1000")
        self.assertEqual(400, response.status_code)

    def test_http_error_invalid_query_param(self):
        response = self.client.get(f"/{API_BASE}/collections?limit=0")
        self.assertEqual(400, response.status_code)
        self._check_http_error_msg(response.json())

    def test_http_error_collection_not_found(self):
        response = self.client.get(f"/{API_BASE}/collections/not-found")
        self.assertEqual(404, response.status_code)
        self._check_http_error_msg(response.json())

    def test_http_error_500_exception(self):
        with self.settings(DEBUG_PROPAGATE_API_EXCEPTIONS=True):
            response = self.client.get("/tests/test_http_500")
            self.assertEqual(500, response.status_code)
            self._check_http_error_msg(response.json())

    def _check_http_error_msg(self, json_msg):
        self.assertListEqual(['code', 'description'],
                             sorted(list(json_msg.keys())),
                             msg="JSON response required keys missing")
        self.assertTrue(isinstance(json_msg['code'], int), msg="'code' is not an integer")
        self.assertTrue(
            isinstance(json_msg['description'], (str, list, dict)), msg="'code' is not an string"
        )

    def test_pagination(self):
        db.create_dummy_db_content(3)

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

    def test_get_precondition(self):
        db.create_dummy_db_content(1, 1, 1)
        for endpoint in [
            'collections/collection-1',
            'collections/collection-1/items/item-1-1',
            'collections/collection-1/items/item-1-1/assets/asset-1-1-1'
        ]:
            with self.subTest(endpoint=endpoint):
                response1 = self.client.get(f"/{API_BASE}/{endpoint}")
                self.assertStatusCode(200, response1)
                # The ETag change between each test call due to the created, updated time that are
                # in the hash computation of the ETag
                self.check_etag(None, response1)

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
        db.create_dummy_db_content(1, 1, 1)
        self.client.login(username=self.username, password=self.password)
        for (endpoint, data) in [
            (
                'collections/collection-1', {
                    'id': 'collection-1',
                    'description': 'test',
                    'license': 'test',
                }
            ),
            (
                'collections/collection-1/items/item-1-1',
                {
                    "id": 'item-1-1',
                    "geometry": TEST_VALID_GEOMETRY,
                    "properties": {
                        "datetime": "2020-10-18T00:00:00Z",
                        "title": "My title",
                    }
                }
            ),
        ]:
            with self.subTest(endpoint=endpoint):
                # Get first the ETag
                response = self.client.get(f"/{API_BASE}/{endpoint}")
                self.assertStatusCode(200, response)
                # The ETag change between each test call due to the created, updated time that are
                # in the hash computation of the ETag
                self.check_etag(None, response)
                etag1 = response['ETag']

                response = self.client.put(
                    f"/{API_BASE}/{endpoint}",
                    data,
                    content_type="application/json",
                    HTTP_IF_MATCH='"abc"'
                )
                self.assertStatusCode(412, response)

                response = self.client.put(
                    f"/{API_BASE}/{endpoint}",
                    data,
                    content_type="application/json",
                    HTTP_IF_MATCH=etag1
                )
                self.assertStatusCode(200, response)
