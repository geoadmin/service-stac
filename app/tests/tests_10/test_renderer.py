from django.test import Client
from django.test import TestCase

from tests.tests_10.base_test import STAC_BASE_V


class RendererTestCase(TestCase):

    def setUp(self):
        self.client = Client()

    def test_content_type_default(self):
        response = self.client.get(f"/{STAC_BASE_V}/search")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json()['type'], 'FeatureCollection')

    def test_content_type_json(self):
        response = self.client.get(f"/{STAC_BASE_V}/search?format=json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json()['type'], 'FeatureCollection')

        response = self.client.get(f"/{STAC_BASE_V}/search", headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json()['type'], 'FeatureCollection')

    def test_content_type_geojson(self):
        response = self.client.get(f"/{STAC_BASE_V}/search?format=geojson")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/geo+json')
        self.assertEqual(response.json()['type'], 'FeatureCollection')

        response = self.client.get(
            f"/{STAC_BASE_V}/search", headers={'Accept': 'application/geo+json'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/geo+json')
        self.assertEqual(response.json()['type'], 'FeatureCollection')
