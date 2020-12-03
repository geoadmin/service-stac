from django.test import Client
from django.test import TestCase

from config.settings import API_BASE


class ConformanceTestCase(TestCase):

    def setUp(self):
        self.client = Client()

    def test_conforms_to_page(self):
        response = self.client.get(f"/{API_BASE}/conformance")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        required_keys = ['conformsTo']
        self.assertEqual(
            set(required_keys).difference(response.json().keys()),
            set(),
            msg="missing required attribute in json answer"
        )

        self.assertGreater(
            len(response.json()['conformsTo']), 0, msg='there are no links defined in conformsTo'
        )
