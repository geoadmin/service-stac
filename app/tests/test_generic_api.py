import logging

from django.conf import settings

from rest_framework.test import APITestCase

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


class ApiGenericTestCase(APITestCase):

    def test_limit_query(self):
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
        self.assertTrue(isinstance(json_msg['description'], str), msg="'code' is not an string")
