import logging

from django.conf import settings

from rest_framework.test import APITestCase

from stac_api.utils import get_link

import tests.database as db
from tests.utils import get_http_error_description

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


class ApiGenericTestCase(APITestCase):

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
