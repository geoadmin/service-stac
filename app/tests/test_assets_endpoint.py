import logging
from json import dumps
from json import loads
from pprint import pformat

from django.conf import settings
from django.test import Client
from django.test import TestCase

from stac_api.serializers import AssetSerializer

import tests.database as db
from tests.utils import get_http_error_description

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


def to_dict(input_ordered_dict):
    return loads(dumps(input_ordered_dict))


class AssetsEndpointTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.collections, self.items, self.assets = db.create_dummy_db_content(4, 4, 2)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_assets_endpoint(self):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].item_name
        response = self.client.get(
            f"/{API_BASE}collections/{collection_name}/items/{item_name}/assets"
        )
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        # Check that the answer is equal to the initial data
        serializer = AssetSerializer(
            self.assets[0][0], many=True, context={'request': response.request}
        )
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            original_data, json_data, msg="Returned data does not match expected data"
        )

    def test_single_asset_endpoint(self):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].item_name
        asset_name = self.assets[0][0][0].asset_name
        response = self.client.get(
            f"/{API_BASE}collections/{collection_name}/items/{item_name}/assets/{asset_name}"
        )
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        # Check that the answer is equal to the initial data
        serializer = AssetSerializer(self.assets[0][0][0], context={'request': response.request})
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            original_data, json_data, msg="Returned data does not match expected data"
        )
