import logging
from pprint import pformat

from django.conf import settings
from django.test import Client
from django.test import TestCase

from rest_framework.test import APIRequestFactory

from stac_api.serializers import CollectionSerializer
from stac_api.utils import fromisoformat

import tests.database as db
from tests.utils import get_http_error_description
from tests.utils import mock_request_from_response

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


class CollectionsEndpointTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.factory = APIRequestFactory()
        self.collections, self.items, self.assets = db.create_dummy_db_content(4, 4, 4)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_collections_endpoint(self):
        response = self.client.get(f"/{API_BASE}/collections")
        response_json = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(response_json))

        # mock the request for creations of links
        request = mock_request_from_response(self.factory, response)

        # transate to Python native:
        serializer = CollectionSerializer(self.collections, many=True, context={'request': request})
        logger.debug('Serialized data:\n%s', pformat(serializer.data))
        logger.debug('Response:\n%s', pformat(response_json))
        self.assertListEqual(
            serializer.data[:2],
            response_json['collections'],
            msg="Returned data does not match expected data"
        )
        self.assertListEqual(['rel', 'href'], list(response_json['links'][0].keys()))

    def test_single_collection_endpoint(self):
        collection_name = self.collections[0].name
        response = self.client.get(f"/{API_BASE}/collections/{collection_name}")
        response_json = response.json()
        self.assertEqual(response.status_code, 200, msg=get_http_error_description(response_json))

        # mock the request for creations of links
        request = mock_request_from_response(self.factory, response)

        # translate to Python native:
        serializer = CollectionSerializer(self.collections, many=True, context={'request': request})
        self.assertDictContainsSubset(
            serializer.data[0], response.data, msg="Returned data does not match expected data"
        )
        # created and updated must exist and be a valid date
        date_fields = ['created', 'updated']
        for date_field in date_fields:
            self.assertTrue(
                fromisoformat(response_json[date_field]),
                msg=f"The field {date_field} has an invalid date"
            )

    def test_collections_limit_query(self):
        response = self.client.get(f"/{API_BASE}/collections?limit=1")
        self.assertEqual(200, response.status_code)
        self.assertLessEqual(1, len(response.json()['collections']))

        response = self.client.get(f"/{API_BASE}/collections?limit=0")
        self.assertEqual(400, response.status_code)

        response = self.client.get(f"/{API_BASE}/collections?limit=test")
        self.assertEqual(400, response.status_code)

        response = self.client.get(f"/{API_BASE}/collections?limit=-1")
        self.assertEqual(400, response.status_code)

        response = self.client.get(f"/{API_BASE}/collections?limit=1000")
        self.assertEqual(400, response.status_code)
