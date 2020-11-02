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
        self.collections, self.items, self.assets = db.create_dummy_db_content(4, 4, 4)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_items_endpoint(self):
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items?format=json"
        )
        self.assertEqual(200, response.status_code)
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        # Check that pagination is present
        self.assertTrue('links' in json_data, msg="'links' missing from repsonce")
        self.assertListEqual([{
            'rel': 'next',
            'href':
                'http://testserver/api/stac/v0.9/collections/collection-1/items?cursor=cD04Mg%3D%3D'
        }], json_data['links']) # yapf: disable

        # Check that the answer is equal to the initial data
        serializer = ItemSerializer(self.items[0][0])
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            original_data,
            json_data['features'][0],
            msg="Returned data does not match expected data"
        )

    def test_single_item_endpoint(self):
        collection_name = self.collections[0].collection_name
        item_name = self.items[0][0].item_name
        response = self.client.get(
            f"/{API_BASE}collections/{collection_name}/items/{item_name}?format=json"
		)
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
