import logging
from json import dumps
from json import loads
from pprint import pformat

from django.conf import settings
from django.test import Client
from django.test import TestCase

from stac_api.serializers import ItemSerializer

import tests.database as db

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


def to_dict(input_ordered_dict):
    return loads(dumps(input_ordered_dict))


class ItemsEndpointTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.nb_collections = 4
        self.nb_items_per_collection = 4
        self.nb_assets_per_item = 4
        self.collections, self.items, self.assets = db.create_dummy_db_content(
            self.nb_collections, self.nb_items_per_collection, self.nb_assets_per_item
        )
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_items_endpoint_with_paging(self):
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items?limit=1"
        )
        self.assertEqual(200, response.status_code)
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        # Check that pagination is present
        self.assertTrue('links' in json_data, msg="'links' missing from response")
        self.assertListEqual(['href', 'rel'],
                             sorted(json_data['links'][0].keys()),
                             msg='Pagination links key missing')
        self.assertEqual('next', json_data['links'][0]['rel'])
        self.assertTrue(isinstance(json_data['links'][0]['href'], str), msg='href is not a string')
        self.assertTrue(
            json_data['links'][0]['href'].
            startswith('http://testserver/api/stac/v0.9/collections/collection-1/items?cursor='),
            msg='Invalid href string'
        )

        # Check that the answer is equal to the initial data
        serializer = ItemSerializer(self.items[0][0])
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            original_data,
            json_data['features'][0],
            msg="Returned data does not match expected data"
        )

    def test_items_endpoints_filtering(self):
        # here we set the limit to the number of items in DB plus one to make
        # sure that the items filtering based on the collection name from uri works
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items?"
            f"limit={self.nb_items_per_collection+1}"
        )
        self.assertEqual(200, response.status_code)
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        self.assertEqual(
            self.nb_items_per_collection, len(json_data['features']), msg="Too many items found"
        )

        # Check that pagination is present response
        self.assertTrue('links' in json_data, msg="'links' missing from response")
        self.assertListEqual([], json_data['links'], msg="should not have pagination")

    def test_single_item_endpoint(self):
        collection_name = self.collections[0].collection_name
        item_name = self.items[0][0].item_name
        response = self.client.get(f"/{API_BASE}collections/{collection_name}/items/{item_name}")
        self.assertEqual(200, response.status_code)
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        # Check that the answer is equal to the initial data
        serializer = ItemSerializer(self.items[0][0])
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            original_data, json_data, msg="Returned data does not match expected data"
        )
