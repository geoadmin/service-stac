from django.test import Client
from django.test import TestCase

from stac_api.serializers import STAC_VERSION

from config.settings import API_BASE


class IndexTestCase(TestCase):

    def setUp(self):
        self.client = Client()

    def test_landing_page(self):
        response = self.client.get(f"/{API_BASE}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        required_keys = ['description', 'id', 'stac_version', 'links']
        self.assertEqual(
            set(required_keys).difference(response.json().keys()),
            set(),
            msg="missing required attribute in json answer"
        )
        self.assertEqual(response.json()['id'], 'ch')
        self.assertEqual(response.json()['stac_version'], STAC_VERSION)
        for link in response.json()['links']:
            required_keys = ['href', 'rel']
            self.assertEqual(
                set(required_keys).difference(link.keys()),
                set(),
                msg="missing required attribute in the answer['links'] array"
            )
