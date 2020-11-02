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
        self.collection = db.create_collection()
        self.item, self.assets = db.create_item(self.collection)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_items_endpoint(self):
        response = self.client.get(
            f"/{API_BASE}collections/{self.collection.collection_name}/items?format=json"
        )
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))
        self.assertEqual(response.status_code, 200)

        # Check that the answer is equal to the initial data
        serializer = ItemSerializer(self.item)
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            json_data['features'][0],
            original_data,
            msg="Returned data does not match expected data"
        )

    def test_single_item_endpoint(self):
        collection_name = self.collection.collection_name
        item_name = self.item.item_name
        response = self.client.get(
            f"/{API_BASE}collections/{collection_name}/items/{item_name}?format=json"
        )
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))
        self.assertEqual(response.status_code, 200)

        # Check that the answer is equal to the initial data
        serializer = ItemSerializer(self.item)
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            json_data, original_data, msg="Returned data does not match expected data"
        )
