import logging

from django.test import Client

from tests.tests_10.base_test import STAC_BASE_V
from tests.tests_10.base_test import StacBaseTestCase

logger = logging.getLogger(__name__)


class SortablesListTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.path = f'/{STAC_BASE_V}/sortables'
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_get_sortables(self):
        response = self.client.get(self.path)
        self.assertStatusCode(200, response)
        self.assertEqual(response['Content-Type'], 'application/schema+json')
        expected_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f'http://testserver/{STAC_BASE_V}/sortables',
            "title": "Sortables",
            "type": "object",
            "properties": {
                "id": {
                    "type": "string"
                },
                "collection": {
                    "type": "string"
                },
                "properties.datetime": {
                    "type": "string",
                    "format": "date-time"
                },
                "properties.title": {
                    "type": "string"
                },
                "properties.created": {
                    "type": "string",
                    "format": "date-time"
                },
                "properties.updated": {
                    "type": "string",
                    "format": "date-time"
                },
            },
            "additionalProperties": False,
        }
        self.assertEqual(response.json(), expected_schema)
