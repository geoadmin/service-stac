from django.test import Client
from django.test import TestCase

from tests.tests_09.base_test import STAC_BASE_V


class ConformanceTestCase(TestCase):

    def setUp(self):
        self.client = Client()

    def test_conforms_to_page(self):
        response = self.client.get(f"/{STAC_BASE_V}/conformance")
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
