from django.test import TestCase
from django.test import Client

from project.settings import API_BASE_PATH


class IndexTestCase(TestCase):

    def setUp(self):
        self.client = Client()

    def test_landing_page(self):
        response = self.client.get(f"/{API_BASE_PATH}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        required_keys = ['description', 'id', 'stac_version', 'links']
        self.assertEqual(
            set(required_keys).difference(response.json().keys()),
            set(),
            msg="missing required attribute in json answer"
        )
        self.assertEqual(response.json()['id'], 'ch')
        self.assertEqual(response.json()['stac_version'], '0.9.0')
        for link in response.json()['links']:
            required_keys = ['href', 'rel']
            self.assertEqual(
                set(required_keys).difference(link.keys()),
                set(),
                msg="missing required attribute in the answer['links'] array"
            )
