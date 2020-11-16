import logging
from datetime import datetime
from datetime import timedelta
from json import dumps
from json import loads
from pprint import pformat

from django.conf import settings
from django.test import Client
from django.test import TestCase

from rest_framework.test import APIRequestFactory

from stac_api.models import Item
from stac_api.serializers import ItemSerializer
from stac_api.utils import isoformat
from stac_api.utils import utc_aware

import tests.database as db
from tests.utils import get_http_error_description
from tests.utils import mock_request_from_response

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


def to_dict(input_ordered_dict):
    return loads(dumps(input_ordered_dict))


class ItemsEndpointTestCase(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.client = Client()
        self.collections, self.items, self.assets = db.create_dummy_db_content(4, 4, 4)
        self.now = utc_aware(datetime.utcnow())
        self.yesterday = self.now - timedelta(days=1)
        item_yesterday = Item.objects.create(
            collection=self.collections[0],
            item_name='item-yesterday',
            properties_datetime=self.yesterday,
            properties_eo_gsd=None,
            properties_title="My Title",
        )
        db.create_item_links(item_yesterday)
        item_yesterday.full_clean()
        item_yesterday.save()
        item_now = Item.objects.create(
            collection=self.collections[0],
            item_name='item-now',
            properties_datetime=self.now,
            properties_eo_gsd=None,
            properties_title="My Title",
        )
        db.create_item_links(item_now)
        item_now.full_clean()
        item_now.save()
        item_range = Item.objects.create(
            collection=self.collections[0],
            item_name='item-range',
            properties_start_datetime=self.yesterday,
            properties_end_datetime=self.now,
            properties_eo_gsd=None,
            properties_title="My Title",
        )
        db.create_item_links(item_range)
        item_range.full_clean()
        item_range.save()
        self.collections[0].save()
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_items_endpoint_with_paging(self):
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items?limit=1"
        )
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))

        # mock the request for creations of links
        request = mock_request_from_response(self.factory, response)

        # Check that pagination is present
        self.assertTrue('links' in json_data, msg="'links' missing from response")
        pagination_links = list(
            filter(
                lambda link: 'rel' in link and link['rel'] in ['next', 'previous'],
                json_data['links']
            )
        )
        self.assertTrue(len(pagination_links) > 0, msg='Pagination links missing')
        for link in pagination_links:
            self.assertListEqual(
                sorted(link.keys()), sorted(['rel', 'href']), msg=f'Link {link} is incomplete'
            )
            self.assertTrue(isinstance(link['href'], str), msg='href is not a string')
            self.assertTrue(
                link['href'].startswith(
                    'http://testserver/api/stac/v0.9/collections/collection-1/items?cursor='
                ),
                msg='Invalid href link pagination string'
            )

        # Check that the answer is equal to the initial data
        serializer = ItemSerializer(self.items[0][0], context={'request': request})
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
            f"limit=100"
        )
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))

        self.assertEqual(7, len(json_data['features']), msg="Too many items found")

        # Check that pagination is present response
        self.assertTrue('links' in json_data, msg="'links' missing from response")
        for link in json_data['links']:
            self.assertNotIn(link['rel'], ['next', 'previous'], msg="should not have pagination")

    def test_single_item_endpoint(self):
        collection_name = self.collections[0].collection_name
        item_name = self.items[0][0].item_name
        response = self.client.get(f"/{API_BASE}collections/{collection_name}/items/{item_name}")
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))

        # mock the request for creations of links
        request = mock_request_from_response(self.factory, response)

        # Check that the answer is equal to the initial data
        serializer = ItemSerializer(self.items[0][0], context={'request': request})
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            original_data, json_data, msg="Returned data does not match expected data"
        )

    def test_items_endpoint_datetime_query(self):
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?datetime={isoformat(self.now)}&limit=10"
        )
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))
        self.assertEqual(1, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-now', json_data['features'][0]['id'])

    def test_items_endpoint_datetime_range_query(self):
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?datetime={isoformat(self.yesterday)}/{isoformat(self.now)}&limit=100"
        )
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))
        self.assertEqual(3, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-yesterday', json_data['features'][0]['id'])
        self.assertEqual('item-now', json_data['features'][1]['id'])

    def test_items_endpoint_datetime_open_end_range_query(self):
        # test open end query
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?datetime={isoformat(self.yesterday)}/..&limit=100"
        )
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))
        self.assertEqual(3, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-yesterday', json_data['features'][0]['id'])
        self.assertEqual('item-now', json_data['features'][1]['id'])

    def test_items_endpoint_datetime_open_start_range_query(self):
        # test open start query
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?datetime=../{isoformat(self.yesterday)}&limit=100"
        )
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))
        self.assertEqual(5, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-yesterday', json_data['features'][-1]['id'])

    def test_items_endpoint_datetime_invalid_range_query(self):
        # test open start and end query
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?datetime=../..&limit=100"
        )
        json_data = response.json()
        self.assertEqual(400, response.status_code, msg=get_http_error_description(json_data))

        # invalid datetime
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?datetime=2019&limit=100"
        )
        json_data = response.json()
        self.assertEqual(400, response.status_code, msg=get_http_error_description(json_data))

        # invalid start
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?datetime=2019/..&limit=100"
        )
        json_data = response.json()
        self.assertEqual(400, response.status_code, msg=get_http_error_description(json_data))

        # invalid end
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?datetime=../2019&limit=100"
        )
        json_data = response.json()
        self.assertEqual(400, response.status_code, msg=get_http_error_description(json_data))

        # invalid start and end
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?datetime=2019/2019&limit=100"
        )
        json_data = response.json()
        self.assertEqual(400, response.status_code, msg=get_http_error_description(json_data))

    def test_items_endpoint_bbox_valid_query(self):
        # test bbox
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?bbox=5.96,45.82,10.49,47.81&limit=100"
        )
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))
        self.assertEqual(7, len(json_data['features']), msg="More than one item found")
        self.assertEqual([5.644711, 46.775054, 7.602408, 49.014995],
                         json_data['features'][0]['bbox'])

    def test_items_endpoint_bbox_invalid_query(self):
        # test invalid bbox
        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?bbox=5.96,45.82,10.49,47.81,screw;&limit=100"
        )
        json_data = response.json()
        self.assertEqual(400, response.status_code, msg=get_http_error_description(json_data))

        response = self.client.get(
            f"/{API_BASE}collections/{self.collections[0].collection_name}/items"
            f"?bbox=5.96,45.82,10.49,47.81,42,42&limit=100"
        )
        json_data = response.json()
        self.assertEqual(400, response.status_code, msg=get_http_error_description(json_data))
