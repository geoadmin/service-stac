import json
import logging
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import quote_plus

from django.test import Client
from django.test import override_settings
from django.utils import timezone

from stac_api.utils import fromisoformat
from stac_api.utils import get_link
from stac_api.utils import isoformat

from tests.tests_10.base_test import STAC_BASE_V
from tests.tests_10.base_test import StacBaseTestCase
from tests.tests_10.data_factory import Factory
from tests.tests_10.utils import reverse_version
from tests.utils import MockS3PerClassMixin

logger = logging.getLogger(__name__)


class SearchEndpointPaginationTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.title_for_query = 'Item for pagination test'
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.items = cls.factory.create_item_samples(
            [
                'item-1',
                'item-2',
                'item-switzerland',
                'item-switzerland-west',
                'item-switzerland-east',
                'item-switzerland-north',
                'item-switzerland-south',
                'item-paris'
            ],
            cls.collection,
            properties_title=[
                'My item',
                cls.title_for_query,
                None,
                'My item',
                'My item',
                cls.title_for_query,
                'My item',
                cls.title_for_query
            ],
            db_create=True,
        )

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.path = f'/{STAC_BASE_V}/search'
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_get_pagination(self):
        limit = 1
        query = {
            "ids": ','.join([self.items[1]['name'], self.items[4]['name'], self.items[6]['name']]),
            "limit": limit
        }
        response = self.client.get(self.path, query)
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), limit)
        # get the next link
        next_link = get_link(json_data['links'], 'next')
        self.assertIsNotNone(next_link, msg='No next link found')
        self.assertEqual(next_link.get('method', 'GET'), 'GET')
        self.assertNotIn('body', next_link)
        self.assertNotIn('merge', next_link)

        # Get the next page
        query_next = query.copy()
        response = self.client.get(next_link['href'])
        self.assertStatusCode(200, response)
        json_data_next = response.json()
        self.assertEqual(len(json_data_next['features']), limit)

        # make sure the next page is different than the original
        self.assertNotEqual(
            json_data['features'],
            json_data_next['features'],
            msg='Next page should not be the same as the first one'
        )

        # get the previous link
        previous_link = get_link(json_data_next['links'], 'previous')
        self.assertIsNotNone(previous_link, msg='No previous link found')
        self.assertEqual(previous_link.get('method', 'GET'), 'GET')
        self.assertNotIn('body', previous_link)
        self.assertNotIn('merge', previous_link)

        # Get the previous page
        response = self.client.get(previous_link['href'])
        self.assertStatusCode(200, response)
        json_data_previous = response.json()
        self.assertEqual(len(json_data_previous['features']), limit)

        # make sure the previous data is identical to the first page
        self.assertEqual(
            json_data_previous['features'],
            json_data['features'],
            msg='previous page should be the same as the first one'
        )

    def test_post_pagination(self):
        limit = 1
        query = {"query": {"title": {"startsWith": self.title_for_query}}, "limit": limit}
        response = self.client.post(self.path, data=query, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), limit)
        # get the next link
        next_link = get_link(json_data['links'], 'next')
        self.assertIsNotNone(next_link, msg='No next link found')
        self.assertEqual(next_link.get('method', 'POST'), 'POST')
        self.assertIn('body', next_link)
        self.assertIn('merge', next_link)

        # Get the next page
        query_next = query.copy()
        if next_link['merge'] and next_link['body']:
            query_next.update(next_link['body'])
        response = self.client.post(
            next_link['href'], data=query_next, content_type="application/json"
        )
        self.assertStatusCode(200, response)
        json_data_next = response.json()
        self.assertEqual(len(json_data_next['features']), limit)

        # make sure the next page is different than the original
        self.assertNotEqual(
            json_data['features'],
            json_data_next['features'],
            msg='Next page should not be the same as the first one'
        )

        # get the previous link
        previous_link = get_link(json_data_next['links'], 'previous')
        self.assertIsNotNone(previous_link, msg='No previous link found')
        self.assertEqual(previous_link.get('method', 'POST'), 'POST')
        self.assertIn('body', previous_link)
        self.assertIn('merge', previous_link)

        # Get the previous page
        query_previous = query.copy()
        if previous_link['merge'] and previous_link['body']:
            query_previous.update(previous_link['body'])
        response = self.client.post(
            previous_link['href'], data=query_previous, content_type="application/json"
        )
        self.assertStatusCode(200, response)
        json_data_previous = response.json()
        self.assertEqual(len(json_data_previous['features']), limit)

        # make sure the previous data is identical to the first page
        self.assertEqual(
            json_data_previous['features'],
            json_data['features'],
            msg='previous page should be the same as the first one'
        )


class SearchEndpointTestCaseOne(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.items = cls.factory.create_item_samples(
            [
                'item-1',
                'item-2',
                'item-switzerland',
                'item-switzerland-west',
                'item-switzerland-east',
                'item-switzerland-north',
                'item-switzerland-south',
                'item-paris'
            ],
            cls.collection,
            db_create=True,
        )
        cls.now = datetime.now(UTC)
        cls.yesterday = cls.now - timedelta(days=1)

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.path = f'/{STAC_BASE_V}/search'
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_query(self):
        # get match
        title = "My item 1"
        query = {"title": {"eq": title}}
        response = self.client.get(f"{self.path}?query={json.dumps(query)}")
        self.assertStatusCode(200, response)
        json_data_get = response.json()
        for feature in json_data_get['features']:
            self.assertEqual(feature['properties']['title'], title)
        self.assertEqual(len(json_data_get['features']), 1)

        # post match
        payload = {"query": {"title": {"eq": "My item 1"}}}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data_post = response.json()
        self.assertEqual(len(json_data_post['features']), 1)

        # compare get and post
        self.assertEqual(json_data_get['features'], json_data_post['features'])

        for feature in json_data_post['features']:
            self.assertEqual(feature['properties']['title'], title)

    def test_query_non_allowed_parameters(self):
        wrong_query_parameter = "cherry"
        payload = {
            wrong_query_parameter: {
                "created": {
                    "lte": "9999-12-31T09:07:39.399892Z"
                }
            }, "limit": 1
        }
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(400, response)
        json_data = response.json()
        self.assertIn(
            wrong_query_parameter,
            str(json_data['description']),
            msg=f"Wrong query parameter {wrong_query_parameter} not found in error message"
        )

    def test_query_multiple_non_allowed_parameters(self):
        wrong_query_parameter1 = "cherry"
        wrong_query_parameter2 = "no_limits"
        payload = {
            wrong_query_parameter1: {
                "created": {
                    "lte": "9999-12-31T09:07:39.399892Z"
                }
            },
            wrong_query_parameter2: 1
        }

        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(400, response)
        json_data = response.json()
        for wrong_par in [wrong_query_parameter1, wrong_query_parameter2]:
            self.assertIn(
                wrong_par,
                str(json_data['description']),
                msg=f"Wrong query parameter {wrong_par} not found in error message"
            )

    def test_limit_in_post(self):
        # limit in payload
        limit = 1
        payload = {'query': {'created': {'lte': '9999-12-31T09:07:39.399892Z'}}, 'limit': limit}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data_payload = response.json()
        self.assertEqual(
            len(json_data_payload['features']), limit, msg=f"More than {limit} item(s) returned."
        )

    def test_query_created(self):
        limit = 1
        # get match
        query = {"created": {"lte": "9999-12-31T09:07:39.399892Z"}}
        response = self.client.get(
            f"/{STAC_BASE_V}/search"
            f"?query={json.dumps(query)}&limit={limit}"
        )
        self.assertStatusCode(200, response)
        json_data_get = response.json()
        self.assertEqual(len(json_data_get['features']), limit)

        # post match
        payload = {"query": query, "limit": limit}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data_post = response.json()
        self.assertEqual(len(json_data_post['features']), limit)
        # compare get and post
        self.assertEqual(
            json_data_get['features'],
            json_data_post['features'],
            msg="GET and POST responses do not match when filtering for date created"
        )
        for feature in json_data_get['features']:
            self.assertLessEqual(
                fromisoformat(feature['properties']['created']),
                fromisoformat(query['created']['lte'])
            )

    def test_query_updated(self):
        limit = 1
        # get match
        query = {"updated": {"lte": "9999-12-31T09:07:39.399892Z"}}
        response = self.client.get(f"{self.path}?query={json.dumps(query)}&limit={limit}")
        self.assertStatusCode(200, response)
        json_data_get = response.json()
        self.assertEqual(len(json_data_get['features']), limit)

        # post match
        payload = {"query": query, "limit": limit}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data_post = response.json()
        self.assertEqual(len(json_data_post['features']), limit)
        # compare get and post
        self.assertEqual(
            json_data_get['features'],
            json_data_post['features'],
            msg="GET and POST responses do not match when filtering for date updated"
        )

        for feature in json_data_get['features']:
            self.assertLessEqual(
                fromisoformat(feature['properties']['updated']),
                fromisoformat(query['updated']['lte'])
            )

    def test_query_data_in(self):
        titles = ["My item 1", "My item 2"]
        payload = {"query": {"title": {"in": titles}}}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        for feature in json_data['features']:
            self.assertIn(feature['properties']['title'], titles)

    def test_post_intersects_valid(self):
        data = {"intersects": {"type": "POINT", "coordinates": [6, 47]}}
        response = self.client.post(self.path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertEqual(json_data['features'][0]['id'], 'item-3')

    def test_get_intersects_valid(self):
        data = {"intersects": {"type": "POINT", "coordinates": [6, 47]}}
        response = self.client.get(f"{self.path}?intersects={json.dumps(data['intersects'])}")
        json_data_get = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(json_data_get['features'][0]['id'], 'item-3')

    def test_post_intersects_invalid(self):
        data = {"intersects": {"type": "POINT", "coordinates": [6, 47, "kaputt"]}}
        response = self.client.post(self.path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_collections_get(self):
        # match
        collections = ['collection-1', 'har']
        response = self.client.get(f"{self.path}?collections={','.join(collections)}")
        self.assertStatusCode(200, response)
        json_data = response.json()
        for feature in json_data['features']:
            self.assertIn(feature['collection'], collections)
        # no match
        response = self.client.get(f"{self.path}?collections=collection-11,har")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 0)

    def test_collections_post_valid(self):
        collections = ["collection-1"]
        payload = {"collections": collections}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        json_data = response.json()
        for feature in json_data['features']:
            self.assertIn(feature['collection'], collections)

    def test_collections_post_invalid(self):
        payload = {"collections": ["collection-1", 9999]}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(400, response)


class SearchEndpointTestCaseTwo(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.items = cls.factory.create_item_samples(
            [
                'item-1',
                'item-2',
                'item-switzerland',
                'item-switzerland-west',
                'item-switzerland-east',
                'item-switzerland-north',
                'item-switzerland-south',
                'item-paris'
            ],
            cls.collection,
            db_create=True,
        )
        cls.now = datetime.now(UTC)
        cls.yesterday = cls.now - timedelta(days=1)

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.path = f'/{STAC_BASE_V}/search'
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_ids_get_valid(self):
        items = ['item-1', 'item-2']
        response = self.client.get(f"{self.path}?ids={','.join(items)}")
        self.assertStatusCode(200, response)
        json_data = response.json()
        for feature in json_data['features']:
            self.assertIn(feature['id'], items)

    def test_ids_post_valid(self):
        items = ['item-1', 'item-2']
        payload = {"ids": items}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        json_data = response.json()
        for feature in json_data['features']:
            self.assertIn(feature['id'], items)

    def test_ids_post_invalid(self):
        payload = {"ids": ["item-1", "item-2", 1]}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_ids_first_and_only_prio(self):
        items = ['item-1', 'item-2']
        response = self.client.get(f"{self.path}?ids={','.join(items)}&collections=not_exist")
        self.assertStatusCode(200, response)
        json_data = response.json()

        for feature in json_data['features']:
            self.assertIn(feature['id'], items)

    def test_bbox_valid(self):
        payload = {"bbox": [6, 47, 6.5, 47.5]}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        json_data_post = response.json()
        list_expected_items = ['item-1', 'item-2']
        self.assertIn(json_data_post['features'][0]['id'], list_expected_items)
        self.assertIn(json_data_post['features'][1]['id'], list_expected_items)

        response = self.client.get(f"{self.path}?bbox={','.join(map(str, payload['bbox']))}")
        json_data_get = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(json_data_get['features'], json_data_post['features'])

    def test_bbox_as_point(self):
        # bbox as a point
        payload = {"bbox": [6.1, 47.1, 6.1, 47.1]}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        json_data_post = response.json()
        list_expected_items = ['item-3', 'item-4', 'item-6']
        self.assertIn(json_data_post['features'][0]['id'], list_expected_items)
        self.assertIn(json_data_post['features'][1]['id'], list_expected_items)
        self.assertIn(json_data_post['features'][2]['id'], list_expected_items)

        response = self.client.get(f"{self.path}?bbox={','.join(map(str, payload['bbox']))}")
        json_data_get = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(json_data_get['features'], json_data_post['features'])

    def test_bbox_post_invalid(self):
        payload = {"bbox": [6, 47, 6.5, 47.5, 5.5]}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_bbox_get_invalid(self):
        response = self.client.get(f"{self.path}?bbox=6,47,6.5,47.5,5.5")
        self.assertStatusCode(400, response)

    def test_datetime_open_end_range_query_get(self):
        response = self.client.get(f"{self.path}?datetime={isoformat(self.yesterday)}/..&limit=100")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(0, len(json_data['features']))

    def test_datetime_open_start_range_query(self):
        response = self.client.get(f"{self.path}?datetime=../{isoformat(self.yesterday)}&limit=100")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(8, len(json_data['features']), msg="Not 8 items found")
        self.assertEqual('item-1', json_data['features'][0]['id'])
        self.assertEqual('item-8', json_data['features'][7]['id'])

        payload = {"datetime": f"../{isoformat(self.yesterday)}"}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data_post = response.json()
        self.assertEqual(json_data_post["features"], json_data["features"])

    def test_datetime_invalid_range_query_get(self):
        response = self.client.get(f"{self.path}?datetime=../..&limit=100")
        self.assertStatusCode(400, response)

    def test_datetime_exact_query_get(self):
        response = self.client.get(f"{self.path}?datetime=2020-10-28T13:05:10Z&limit=100")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(7, len(json_data['features']), msg="Seven items Found")
        self.assertEqual('item-1', json_data['features'][0]['id'])
        self.assertEqual('item-8', json_data['features'][6]['id'])

    def test_datetime_invalid_format_query_get(self):
        response = self.client.get(f"/{STAC_BASE_V}/search?datetime=NotADate&limit=100")
        self.assertStatusCode(400, response)

    def test_get_does_not_show_expired_items(self):
        tomorrow = timezone.now() + timedelta(days=1)
        self.factory.create_item_sample(
            self.collection, name='item-expired', db_create=True, properties_expires=tomorrow
        )
        in_a_week = timezone.now() + timedelta(days=7)
        self.factory.create_item_sample(
            self.collection,
            name='item-with-expiration-date-but-active',
            db_create=True,
            properties_expires=in_a_week
        )

        after_tomorrow = timezone.now() + timedelta(days=2)
        with patch.object(timezone, "now", return_value=after_tomorrow):
            response = self.client.get(self.path)

        self.assertStatusCode(200, response)
        feature_ids = [feature["id"] for feature in response.json()['features']]
        self.assertNotIn('item-expired', feature_ids)
        self.assertIn('item-with-expiration-date-but-active', feature_ids)

    def test_post_does_not_show_expired_items(self):
        tomorrow = timezone.now() + timedelta(days=1)
        self.factory.create_item_sample(
            self.collection, name='item-expired', db_create=True, properties_expires=tomorrow
        )
        in_a_week = timezone.now() + timedelta(days=7)
        self.factory.create_item_sample(
            self.collection,
            name='item-with-expiry-date-but-active',
            db_create=True,
            properties_expires=in_a_week
        )

        after_tomorrow = timezone.now() + timedelta(days=2)
        with patch.object(timezone, "now", return_value=after_tomorrow):
            response = self.client.post(self.path)

        self.assertStatusCode(200, response)
        feature_ids = [feature["id"] for feature in response.json()['features']]
        self.assertNotIn('item-expired', feature_ids)
        self.assertIn('item-with-expiry-date-but-active', feature_ids)


@override_settings(CACHE_MIDDLEWARE_SECONDS=3600)
class SearchEndpointCacheSettingTestCase(MockS3PerClassMixin, StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.title_for_query = 'Item for cache settings test'
        cls.factory = Factory()
        cls.collections = cls.factory.create_collection_samples(3, db_create=True)
        cls.items = [
            item for items in map(
                cls.factory.create_item_samples,
                [10] * len(cls.collections),
                map(lambda c: c.model, cls.collections),
                [True] * len(cls.collections),) for item in items
        ]
        cls.assets = [
            asset for assets in map(
                cls.factory.create_asset_samples,
                [3] * len(cls.items),
                map(lambda i: i.model, cls.items),
                [True] * len(cls.items),) for asset in assets
        ]

    def test_get_search_dft_cache_setting(self):
        response = self.client.get(reverse_version('search-list'))
        self.assertStatusCode(200, response)
        self.assertCacheControl(response, no_cache=True)

    def test_get_search_no_cache_setting(self):
        self.factory.create_asset_sample(self.items[0].model, db_create=True)
        response = self.client.get(reverse_version('search-list'))
        self.assertStatusCode(200, response)
        self.assertCacheControl(response, no_cache=True)

    def test_get_search_no_cache_setting_paging(self):
        self.factory.create_asset_sample(self.items[-1].model, db_create=True)
        response = self.client.get(reverse_version('search-list'), QUERY_STRING="limit=1")
        self.assertStatusCode(200, response)
        self.assertCacheControl(response, no_cache=True)

    def test_post_search_no_cache_setting(self):
        response = self.client.post(reverse_version('search-list'))
        self.assertStatusCode(200, response)
        self.assertFalse(
            response.has_header('Cache-Control'),
            msg="Unexpected Cache-Control header in POST response"
        )
        self.factory.create_asset_sample(self.items[0].model, db_create=True)
        response = self.client.post(reverse_version('search-list'))
        self.assertStatusCode(200, response)
        self.assertFalse(
            response.has_header('Cache-Control'),
            msg="Unexpected Cache-Control header in POST response"
        )


class SearchEndpointTestForecast(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.factory.create_item_sample(
            cls.collection, 'item-forecast-1', 'item-forecast-1', db_create=True
        )
        cls.factory.create_item_sample(
            cls.collection, 'item-forecast-2', 'item-forecast-2', db_create=True
        )
        cls.factory.create_item_sample(
            cls.collection, 'item-forecast-3', 'item-forecast-3', db_create=True
        )
        cls.factory.create_item_sample(
            cls.collection, 'item-forecast-4', 'item-forecast-4', db_create=True
        )
        cls.factory.create_item_sample(
            cls.collection, 'item-forecast-5', 'item-forecast-5', db_create=True
        )
        cls.now = datetime.now(UTC)
        cls.yesterday = cls.now - timedelta(days=1)

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.path = f'/{STAC_BASE_V}/search'
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_reference_datetime_exact(self):
        payload = {"forecast:reference_datetime": "2025-01-01T13:05:10Z"}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 1)
        for feature in json_data['features']:
            self.assertIn(feature['id'], ['item-forecast-1'])

        payload = {"forecast:reference_datetime": "2025-02-01T13:05:10Z"}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 3)
        for feature in json_data['features']:
            self.assertIn(feature['id'], ['item-forecast-2', 'item-forecast-3', 'item-forecast-4'])

    def test_reference_datetime_range(self):
        payload = {"forecast:reference_datetime": "2025-02-01T00:00:00Z/2025-02-28T00:00:00Z"}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 3)
        for feature in json_data['features']:
            self.assertIn(feature['id'], ['item-forecast-2', 'item-forecast-3', 'item-forecast-4'])

    def test_reference_datetime_open_end(self):
        payload = {"forecast:reference_datetime": "2025-02-01T13:05:10Z/.."}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 4)
        for feature in json_data['features']:
            self.assertIn(
                feature['id'],
                ['item-forecast-2', 'item-forecast-3', 'item-forecast-4', 'item-forecast-5']
            )

    def test_reference_datetime_open_start(self):
        payload = {"forecast:reference_datetime": "../2025-02-01T13:05:10Z"}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 4)
        for feature in json_data['features']:
            self.assertIn(
                feature['id'],
                ['item-forecast-1', 'item-forecast-2', 'item-forecast-3', 'item-forecast-4']
            )

    def test_horizon(self):
        payload = {"forecast:horizon": "PT3H"}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 1)
        for feature in json_data['features']:
            self.assertIn(feature['id'], ['item-forecast-3'])

    def test_duration(self):
        payload = {"forecast:duration": "PT12H"}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 4)
        for feature in json_data['features']:
            self.assertIn(
                feature['id'],
                ['item-forecast-1', 'item-forecast-2', 'item-forecast-4', 'item-forecast-5']
            )

    def test_variable(self):
        payload = {"forecast:variable": "air_temperature"}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 2)
        for feature in json_data['features']:
            self.assertIn(feature['id'], ['item-forecast-4', 'item-forecast-5'])

    def test_perturbed(self):
        payload = {"forecast:perturbed": "True"}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 1)
        for feature in json_data['features']:
            self.assertIn(feature['id'], ['item-forecast-4'])

    def test_multiple(self):
        payload = {
            "forecast:perturbed": "False", "forecast:horizon": "PT6H", "forecast:variable": "T"
        }
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 2)
        for feature in json_data['features']:
            self.assertIn(feature['id'], ['item-forecast-1', 'item-forecast-2'])

    def test_get_request_does_not_filter_forecast(self):
        response = self.client.get(
            f"{self.path}?" + quote_plus(
                "forecast:reference_datetime=2025-01-01T13:05:10Z&" + "forecast:duration=PT12H&" +
                "forecast:perturbed=False&" + "forecast:horizon=PT6H&" + "forecast:variable=T"
            )
        )
        self.assertStatusCode(200, response)
        json_data = response.json()
        # As GET request should not filter for forecast expect all 5 features to be returned.
        self.assertEqual(len(json_data['features']), 5)
