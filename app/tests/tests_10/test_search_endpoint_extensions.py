import logging
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest import skip
from urllib.parse import quote_plus

from django.test import Client
from django.utils import timezone

from stac_api.utils import fromisoformat

from tests.tests_10.base_test import STAC_BASE_V
from tests.tests_10.base_test import StacBaseTestCase
from tests.tests_10.data_factory import Factory

logger = logging.getLogger(__name__)


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


class SearchEndpointTestCF(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.factory.create_item_sample(cls.collection, 'item-cf-1', 'item-cf-1', db_create=True)
        cls.factory.create_item_sample(cls.collection, 'item-cf-2', 'item-cf-2', db_create=True)
        cls.factory.create_item_sample(cls.collection, 'item-cf-3', 'item-cf-3', db_create=True)

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.path = f'/{STAC_BASE_V}/search'
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_cf_standard_name(self):
        payload = {"query": {"cf:standard_name": {"eq": "air_temperature"}}}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 2)
        for feature in json_data['features']:
            self.assertIn(feature['id'], ['item-cf-1', 'item-cf-2'])

    def test_unit(self):
        payload = {"query": {"unit": {"eq": "K"}}}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 1)
        for feature in json_data['features']:
            self.assertIn(feature['id'], ['item-cf-1'])

    @skip(
        "PB-2354: Known bug - Cannot filter by multiple fields. "
        "Will be fixed by implementing Filter Extension instead."
    )
    def test_multiple_cf(self):
        payload = {"query": {"cf:standard_name": {"eq": "air_temperature"}, "unit": {"eq": "K"}}}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 1)
        for feature in json_data['features']:
            self.assertIn(feature['id'], ['item-cf-1'])

    def test_cf_standard_name_invalid_as_direct_param(self):
        payload = {"cf:standard_name": "air_temperature"}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_unit_invalid_as_direct_param(self):
        payload = {"unit": "K"}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_get_request_does_not_filter_cf(self):
        response = self.client.get(
            f"{self.path}?" + quote_plus("cf:standard_name=air_temperature&" + "unit=K")
        )
        self.assertStatusCode(200, response)
        json_data = response.json()
        # As GET request should not filter for CF expect all 3 features to be returned.
        self.assertEqual(len(json_data['features']), 3)


class SearchEndpointSortTestCase(StacBaseTestCase):
    '''Tests for the sortby parameter on the GET and POST /search endpoint'''

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        # Give item-1 and item-2 distinct datetimes so that sorting by
        # properties.datetime is fully deterministic (no tie-breaking).
        cls.items = [
            cls.factory.create_item_sample(
                cls.collection,
                name='item-1',
                sample='item-1',
                properties_datetime=fromisoformat('2020-10-28T13:05:10Z'),
                db_create=True
            ),
            cls.factory.create_item_sample(
                cls.collection,
                name='item-2',
                sample='item-1',
                properties_datetime=fromisoformat('2020-10-29T13:05:10Z'),
                db_create=True
            )
        ]

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.path = f'/{STAC_BASE_V}/search'
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_get_sortby_id_ascending(self):
        response = self.client.get(f"{self.path}?sortby=id")
        self.assertStatusCode(200, response)
        item_ids = [item['id'] for item in response.json()['features']]
        self.assertEqual(item_ids, ["item-1", "item-2"])

    def test_get_sortby_id_descending(self):
        response = self.client.get(f"{self.path}?sortby=-id")
        self.assertStatusCode(200, response)
        item_ids = [item['id'] for item in response.json()['features']]
        self.assertEqual(item_ids, ["item-2", "item-1"])

    def test_get_sortby_properties_datetime(self):
        self.factory.create_item_sample(
            self.collection,
            name='item-dt-1',
            properties_datetime=timezone.now() + timedelta(days=2),
            db_create=True
        )
        self.factory.create_item_sample(
            self.collection,
            name='item-dt-2',
            properties_datetime=timezone.now() + timedelta(days=1),
            db_create=True
        )
        self.factory.create_item_sample(
            self.collection,
            name='item-dt-3',
            properties_datetime=timezone.now() + timedelta(days=3),
            db_create=True
        )

        # ascending sort
        response = self.client.get(f"{self.path}?sortby=properties.datetime")
        self.assertStatusCode(200, response)
        item_ids = [item['id'] for item in response.json()['features']]
        self.assertEqual(item_ids, ['item-1', 'item-2', 'item-dt-2', 'item-dt-1', 'item-dt-3'])

        # descending sort
        response = self.client.get(f"{self.path}?sortby=-properties.datetime")
        self.assertStatusCode(200, response)
        item_ids = [item['id'] for item in response.json()['features']]
        self.assertEqual(item_ids, ['item-dt-3', 'item-dt-1', 'item-dt-2', 'item-2', 'item-1'])

    def test_get_sortby_multiple_fields(self):
        tomorrow = timezone.now() + timedelta(days=1)
        self.factory.create_item_sample(
            self.collection,
            name='item-multi-1',
            properties_datetime=tomorrow,
            properties_title='AAA',
            db_create=True
        )
        self.factory.create_item_sample(
            self.collection,
            name='item-multi-2',
            properties_datetime=tomorrow,
            properties_title='BBB',
            db_create=True
        )
        self.factory.create_item_sample(
            self.collection,
            name='item-multi-3',
            properties_datetime=tomorrow + timedelta(days=1),
            properties_title='CCC',
            db_create=True
        )

        # Sort by datetime ascending, then by title descending
        response = self.client.get(f"{self.path}?sortby=properties.datetime,-properties.title")
        self.assertStatusCode(200, response)
        item_ids = [item['id'] for item in response.json()['features']]
        self.assertEqual(
            item_ids, ['item-1', 'item-2', 'item-multi-2', 'item-multi-1', 'item-multi-3']
        )

    def test_get_sortby_invalid_field(self):
        response = self.client.get(f"{self.path}?sortby=expires")
        self.assertStatusCode(400, response)

    def test_post_sortby_empty_list(self):
        payload = {"sortby": []}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        item_ids = [item['id'] for item in response.json()['features']]
        self.assertEqual(item_ids, ["item-1", "item-2"])

    def test_post_sortby_id_ascending(self):
        payload = {"sortby": [{"field": "id", "direction": "asc"}]}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        item_ids = [item['id'] for item in response.json()['features']]
        self.assertEqual(item_ids, ["item-1", "item-2"])

    def test_post_sortby_id_descending(self):
        payload = {"sortby": [{"field": "id", "direction": "desc"}]}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        item_ids = [item['id'] for item in response.json()['features']]
        self.assertEqual(item_ids, ["item-2", "item-1"])

    def test_post_sortby_properties_datetime(self):
        self.factory.create_item_sample(
            self.collection,
            name='item-dt-1',
            properties_datetime=timezone.now() + timedelta(days=2),
            db_create=True
        )
        self.factory.create_item_sample(
            self.collection,
            name='item-dt-2',
            properties_datetime=timezone.now() + timedelta(days=1),
            db_create=True
        )
        self.factory.create_item_sample(
            self.collection,
            name='item-dt-3',
            properties_datetime=timezone.now() + timedelta(days=3),
            db_create=True
        )

        # ascending sort
        payload = {"sortby": [{"field": "properties.datetime", "direction": "asc"}]}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        item_ids = [item['id'] for item in response.json()['features']]
        self.assertEqual(item_ids, ['item-1', 'item-2', 'item-dt-2', 'item-dt-1', 'item-dt-3'])

        # descending sort
        payload = {"sortby": [{"field": "properties.datetime", "direction": "desc"}]}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        item_ids = [item['id'] for item in response.json()['features']]
        self.assertEqual(item_ids, ['item-dt-3', 'item-dt-1', 'item-dt-2', 'item-2', 'item-1'])

    def test_post_sortby_multiple_fields(self):
        tomorrow = timezone.now() + timedelta(days=1)
        self.factory.create_item_sample(
            self.collection,
            name='item-multi-1',
            properties_datetime=tomorrow,
            properties_title='AAA',
            db_create=True
        )
        self.factory.create_item_sample(
            self.collection,
            name='item-multi-2',
            properties_datetime=tomorrow,
            properties_title='BBB',
            db_create=True
        )
        self.factory.create_item_sample(
            self.collection,
            name='item-multi-3',
            properties_datetime=tomorrow + timedelta(days=1),
            properties_title='CCC',
            db_create=True
        )

        # Sort by datetime ascending, then by title descending
        payload = {
            "sortby": [{
                "field": "properties.datetime", "direction": "asc"
            }, {
                "field": "properties.title", "direction": "desc"
            }]
        }
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        item_ids = [item['id'] for item in response.json()['features']]
        self.assertEqual(
            item_ids, ['item-1', 'item-2', 'item-multi-2', 'item-multi-1', 'item-multi-3']
        )

    def test_post_sortby_invalid_field(self):
        payload = {"sortby": [{"field": "expires", "direction": "asc"}]}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_post_sortby_invalid_direction(self):
        payload = {"sortby": [{"field": "id", "direction": "sideways"}]}
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(400, response)
