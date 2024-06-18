from django.test import Client

from tests.tests_09.base_test import STAC_BASE_V
from tests.tests_09.base_test import STAC_VERSION
from tests.tests_09.base_test import StacBaseTestCase


class IndexTestCase(StacBaseTestCase):

    def setUp(self):
        self.client = Client()

    def test_landing_page(self):
        response = self.client.get(f"/{STAC_BASE_V}/")
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

    def test_landing_page_redirect(self):
        response = self.client.get(f"/{STAC_BASE_V}")
        self.assertEqual(response.status_code, 301)
        self.assertLocationHeader(f"/{STAC_BASE_V}/", response)
        self.assertCors(response)
