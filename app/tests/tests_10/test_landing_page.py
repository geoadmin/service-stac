from parameterized import parameterized

from django.test import Client

from tests.tests_10.base_test import STAC_BASE_V
from tests.tests_10.base_test import STAC_VERSION
from tests.tests_10.base_test import StacBaseTestCase


class IndexTestCase(StacBaseTestCase):

    def setUp(self):
        self.client = Client()

    @parameterized.expand([
        (f"/{STAC_BASE_V}/",),
        (f"/{STAC_BASE_V}",),
    ])
    def test_landing_page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertCors(response)
        self.assertEqual(response['Content-Type'], 'application/json')
        required_keys = ['description', 'id', 'stac_version', 'links', 'type']
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
