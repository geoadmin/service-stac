from django.test import Client
from django.test import TestCase

from tests.tests_10.base_test import STAC_BASE_V


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

    def test_sort_conformance_classes(self):
        sort_conformance_classes = [
            'https://api.stacspec.org/v1.1.0/item-search#sort',
            'https://api.stacspec.org/v1.1.0/ogcapi-features#sort',
            'https://api.stacspec.org/v1.1.0/item-search#sortables',
            'http://www.opengis.net/spec/ogcapi-features-5/1.0/conf/sortables',
        ]
        response = self.client.get(f"/{STAC_BASE_V}/conformance")
        self.assertEqual(response.status_code, 200)
        conforms_to = response.json()['conformsTo']
        for conformance_class in sort_conformance_classes:
            self.assertIn(
                conformance_class,
                conforms_to,
                msg=f"missing conformance class: {conformance_class}"
            )
