import logging

from django.test import Client

from tests.tests_10.base_test import STAC_BASE_V
from tests.tests_10.base_test import StacBaseTestCase
from tests.tests_10.data_factory import Factory

logger = logging.getLogger(__name__)


class SortablesTestCase(StacBaseTestCase):

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
                "datetime": {
                    "type": "string", "format": "date-time"
                },
                "title": {
                    "type": "string"
                },
                "created": {
                    "type": "string", "format": "date-time"
                },
                "updated": {
                    "type": "string", "format": "date-time"
                },
            },
            "additionalProperties": False,
        }
        self.assertEqual(response.json(), expected_schema)

    def test_get_sortables_accept_schema_json(self):
        response = self.client.get(self.path, HTTP_ACCEPT='application/schema+json')
        self.assertStatusCode(200, response)
        self.assertEqual(response['Content-Type'], 'application/schema+json')


class CollectionSortablesTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):  # pylint: disable=invalid-name
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.collection_name = self.collection.name
        self.path = f'/{STAC_BASE_V}/collections/{self.collection_name}/sortables'
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_get_collection_sortables(self):
        response = self.client.get(self.path)
        self.assertStatusCode(200, response)
        self.assertEqual(response['Content-Type'], 'application/schema+json')
        expected_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f'http://testserver/{STAC_BASE_V}/collections/{self.collection_name}/sortables',
            "title": "Sortables",
            "type": "object",
            "properties": {
                "id": {
                    "type": "string"
                },
                "collection": {
                    "type": "string"
                },
                "datetime": {
                    "type": "string", "format": "date-time"
                },
                "title": {
                    "type": "string"
                },
                "created": {
                    "type": "string", "format": "date-time"
                },
                "updated": {
                    "type": "string", "format": "date-time"
                },
            },
            "additionalProperties": False,
        }
        self.assertEqual(response.json(), expected_schema)

    def test_get_collection_sortables_accept_schema_json(self):
        response = self.client.get(self.path, HTTP_ACCEPT='application/schema+json')
        self.assertStatusCode(200, response)
        self.assertEqual(response['Content-Type'], 'application/schema+json')

    def test_get_collection_sortables_not_found(self):
        response = self.client.get(f'/{STAC_BASE_V}/collections/nonexistent/sortables')
        self.assertStatusCode(404, response)

    def test_collection_detail_has_sortables_link(self):
        response = self.client.get(f'/{STAC_BASE_V}/collections/{self.collection_name}')
        self.assertStatusCode(200, response)
        expected_link = {
            "rel": "http://www.opengis.net/def/rel/ogc/1.0/sortables",
            "href": f'http://testserver/{STAC_BASE_V}/collections/{self.collection_name}/sortables',
            "type": "application/schema+json",
            "title": "Sortable fields for the sortby parameter",
        }
        sortables_links = [
            link for link in response.json()['links']
            if link['rel'] == "http://www.opengis.net/def/rel/ogc/1.0/sortables"
        ]
        self.assertEqual(sortables_links, [expected_link])
