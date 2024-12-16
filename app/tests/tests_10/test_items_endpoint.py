# pylint: disable=too-many-lines
import logging
from datetime import datetime
from datetime import timedelta
from typing import cast

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from stac_api.models import Collection
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.utils import fromisoformat
from stac_api.utils import get_link
from stac_api.utils import isoformat
from stac_api.utils import utc_aware

from tests.tests_10.base_test import STAC_BASE_V
from tests.tests_10.base_test import StacBaseTestCase
from tests.tests_10.base_test import StacBaseTransactionTestCase
from tests.tests_10.data_factory import CollectionFactory
from tests.tests_10.data_factory import Factory
from tests.tests_10.data_factory import ItemFactory
from tests.tests_10.utils import reverse_version
from tests.utils import client_login
from tests.utils import disableLogger
from tests.utils import mock_s3_asset_file

from .data_factory import SampleData

logger = logging.getLogger(__name__)


class ItemsReadEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.items = cls.factory.create_item_samples(
            2, cls.collection, name=['item-1', 'item-2'], db_create=True
        )

    def setUp(self):
        self.client = Client()

    @mock_s3_asset_file
    def test_items_endpoint(self):
        # To make sure that item sorting is working, make sure that the items where not
        # created in ascending order, same for assets
        item_3 = self.factory.create_item_sample(self.collection, name='item-0', db_create=True)
        # created item that is expired should not show up in the get result
        self.factory.create_item_sample(
            self.collection,
            name='item-expired',
            db_create=True,
            properties_expires=timezone.now() - timedelta(hours=1)
        )
        assets = self.factory.create_asset_samples(
            3, item_3.model, name=['asset-1.tiff', 'asset-0.tiff', 'asset-2.tiff'], db_create=True
        )
        response = self.client.get(f"/{STAC_BASE_V}/collections/{self.collection.name}/items")
        self.assertStatusCode(200, response)
        json_data = response.json()

        self.assertEqual(
            len(json_data['features']), 3, msg='Output should only have three features'
        )

        # Check that the output is sorted by name
        item_ids = [item['id'] for item in json_data['features']]
        self.assertListEqual(item_ids, sorted(item_ids), msg="Items are not sorted by ID")

        item_samples = sorted(self.items + [item_3], key=lambda item: item['name'])
        for i, item in enumerate(item_samples):
            self.check_stac_item(item.json, json_data['features'][i], self.collection.name)

        self.assertEqual(
            len(json_data['features'][0]['assets']), 3, msg="Integrated assets length don't match"
        )

        # Check that the integrated assets output is sorted by name
        asset_ids = list(json_data['features'][0]['assets'].keys())
        self.assertListEqual(
            asset_ids, sorted(asset_ids), msg="Integrated assets are not sorted by ID"
        )

        # Check the integrated assets output
        asset_samples = sorted(assets, key=lambda asset: asset['name'])
        for asset in asset_samples:
            self.check_stac_asset(
                asset.json,
                json_data['features'][0]['assets'][asset['name']],
                self.collection.name,
                json_data['features'][0]['id'],
                # in the integrated asset there is no id (the id is actually the json key)
                ignore=['id', 'links']
            )

    def test_items_endpoint_with_limit(self):
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items?limit=1"
        )
        self.assertStatusCode(200, response)
        json_data = response.json()

        # Check that pagination is present
        self.assertTrue('links' in json_data, msg="'links' missing from response")

        self.assertEqual(len(json_data['features']), 1, msg='Output should only have one feature')

        self.check_stac_item(self.items[0].json, json_data['features'][0], self.collection.name)

    def test_single_item_endpoint(self):
        collection_name = self.collection.name
        item = self.items[0]
        # create assets in a non ascending order to make sure that the assets ordering is working
        assets = self.factory.create_asset_samples(
            3, item.model, name=['asset-1.tiff', 'asset-0.tiff', 'asset-2.tiff'], db_create=True
        )
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{collection_name}/items/{item['name']}"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)

        # The ETag change between each test call due to the created, updated time that are in the
        # hash computation of the ETag
        self.assertEtagHeader(None, response)

        self.check_stac_item(item.json, json_data, self.collection.name)

        # created and updated must exist and be a valid date
        date_fields = ['created', 'updated']
        for date_field in date_fields:
            self.assertTrue(
                fromisoformat(json_data['properties'][date_field]),
                msg=f"The field {date_field} has an invalid date"
            )

        self.assertEqual(len(json_data['assets']), 3, msg="Integrated assets length don't match")

        # Check that the integrated assets output is sorted by name
        asset_ids = list(json_data['assets'].keys())
        self.assertListEqual(
            asset_ids, sorted(asset_ids), msg="Integrated assets are not sorted by ID"
        )

        # Check the integrated assets output
        asset_samples = sorted(assets, key=lambda asset: asset['name'])
        for asset in asset_samples:
            self.check_stac_asset(
                asset.json,
                json_data['assets'][asset['name']],
                collection_name,
                json_data['id'],
                # in the integrated asset there is no id (the id is actually the json key)
                ignore=['id', 'links']
            )

    def test_single_item_endpoint_expired(self):
        collection_name = self.collection.name
        # created item that is expired should not be found
        item = self.factory.create_item_sample(
            self.collection,
            name='item-expired',
            db_create=True,
            properties_expires=timezone.now() - timedelta(hours=1)
        )

        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{collection_name}/items/{item['name']}"
        )
        self.assertStatusCode(404, response)

    def test_items_endpoint_non_existing_collection(self):
        response = self.client.get(f"/{STAC_BASE_V}/collections/non-existing-collection/items")
        self.assertStatusCode(404, response)


class ItemsDatetimeQueryEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model

        cls.item_1 = cls.factory.create_item_sample(
            cls.collection,
            name='item-1',
            properties_datetime=fromisoformat('2019-01-01T00:00:00Z'),
            db_create=True,
        )

        cls.now = utc_aware(datetime.utcnow())
        cls.yesterday = cls.now - timedelta(days=1)

        cls.item_now = cls.factory.create_item_sample(
            cls.collection,
            name='item-now',
            properties_datetime=cls.now,
            db_create=True,
        )
        cls.item_yesterday = cls.factory.create_item_sample(
            cls.collection,
            name='item-yesterday',
            properties_datetime=cls.yesterday,
            db_create=True
        )

    def setUp(self):
        self.client = Client()

    def test_items_endpoint_datetime_query(self):
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime={isoformat(self.now)}&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(1, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-now', json_data['features'][0]['id'])

    def test_items_endpoint_datetime_range_query(self):
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime={isoformat(self.yesterday)}/{isoformat(self.now)}&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(2, len(json_data['features']), msg="More than two item found")
        self.assertEqual('item-yesterday', json_data['features'][1]['id'])
        self.assertEqual('item-now', json_data['features'][0]['id'])

    def test_items_endpoint_datetime_open_end_range_query(self):
        # test open end query
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime={isoformat(self.yesterday)}/..&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(2, len(json_data['features']), msg="More than two item found")
        self.assertEqual('item-yesterday', json_data['features'][1]['id'])
        self.assertEqual('item-now', json_data['features'][0]['id'])

    def test_items_endpoint_datetime_open_start_range_query(self):
        # test open start query
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime=../{isoformat(self.yesterday)}&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(2, len(json_data['features']), msg="More than two item found")
        self.assertEqual('item-1', json_data['features'][0]['id'])
        self.assertEqual('item-yesterday', json_data['features'][1]['id'])

    def test_items_endpoint_datetime_invalid_range_query(self):
        # test open start and end query
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime=../..&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid datetime
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime=2019&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid start
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime=2019/..&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid end
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime=../2019&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid start and end
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime=2019/2019&limit=100"
        )
        self.assertStatusCode(400, response)


class ItemsDatetimeQueryPaginationEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model

        cls.items = cls.factory.create_item_samples(
            2,
            cls.collection,
            name=['item-1', 'item-2'],
            properties_datetime=fromisoformat('2019-01-01T00:00:00Z'),
            db_create=True,
        )

        cls.now = utc_aware(datetime.utcnow())
        cls.yesterday = cls.now - timedelta(days=1)

        cls.items_now = cls.factory.create_item_samples(
            2,
            cls.collection,
            name=['item-now-1', 'item-now-2'],
            properties_datetime=cls.now,
            db_create=True,
        )
        cls.items_yesterday = cls.factory.create_item_samples(
            2,
            cls.collection,
            name=['item-yesterday-1', 'item-yesterday-2'],
            properties_datetime=cls.yesterday,
            db_create=True
        )

    def setUp(self):
        self.client = Client()

    def _navigate_to_next_items(self, expected_items, json_response):
        for expected_item in expected_items:
            self.assertIn('links', json_response, msg='No links found in answer')
            next_link = get_link(json_response['links'], 'next')
            self.assertIsNotNone(
                next_link, msg=f'No next link found in links: {json_response["links"]}'
            )
            self.assertIn('href', next_link, msg=f'Next link has no href: {next_link}')
            response = self.client.get(next_link['href'])
            json_response = response.json()
            self.assertStatusCode(200, response)
            self.assertEqual(1, len(json_response['features']), msg="More than one item found")
            self.assertEqual(expected_item, json_response['features'][0]['id'])

        # Make sure there is no next link
        self.assertIn('links', json_response, msg='No links found in answer')
        self.assertIsNone(get_link(json_response['links'], 'next'), msg='Should not have next link')

        return json_response

    def _navigate_to_previous_items(self, expected_items, json_response):
        for expected_item in expected_items:
            self.assertIn('links', json_response, msg='No links found in answer')
            previous_link = get_link(json_response['links'], 'previous')
            self.assertIsNotNone(
                previous_link, msg=f'No previous link found in links: {json_response["links"]}'
            )
            self.assertIn('href', previous_link, msg=f'Previous link has no href: {previous_link}')
            response = self.client.get(previous_link['href'])
            json_response = response.json()
            self.assertStatusCode(200, response)
            self.assertEqual(1, len(json_response['features']), msg="More than one item found")
            self.assertEqual(expected_item, json_response['features'][0]['id'])

        # Make sure there is no previous link
        self.assertIn('links', json_response, msg='No links found in answer')
        self.assertIsNone(
            get_link(json_response['links'], 'previous'), msg='Should not have previous link'
        )

        return json_response

    def test_items_endpoint_datetime_query(self):
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime={isoformat(self.now)}&limit=1"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(1, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-now-1', json_data['features'][0]['id'])

        json_response = self._navigate_to_next_items(['item-now-2'], json_data)

        self._navigate_to_previous_items(['item-now-1'], json_response)

    def test_items_endpoint_datetime_range_query(self):
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime={isoformat(self.yesterday)}/{isoformat(self.now)}&limit=1"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(1, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-now-1', json_data['features'][0]['id'])

        json_response = self._navigate_to_next_items(
            ['item-now-2', 'item-yesterday-1', 'item-yesterday-2'],
            json_data,
        )

        self._navigate_to_previous_items(['item-yesterday-1', 'item-now-2', 'item-now-1'],
                                         json_response)

    def test_items_endpoint_datetime_open_end_range_query(self):
        # test open end query
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime={isoformat(self.yesterday)}/..&limit=1"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(1, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-now-1', json_data['features'][0]['id'])

        json_response = self._navigate_to_next_items(
            ['item-now-2', 'item-yesterday-1', 'item-yesterday-2'],
            json_data,
        )

        self._navigate_to_previous_items(['item-yesterday-1', 'item-now-2', 'item-now-1'],
                                         json_response)

    def test_items_endpoint_datetime_open_start_range_query(self):
        # test open start query
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?datetime=../{isoformat(self.yesterday)}&limit=1"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(1, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-1', json_data['features'][0]['id'])

        json_response = self._navigate_to_next_items(
            ['item-2', 'item-yesterday-1', 'item-yesterday-2'],
            json_data,
        )

        self._navigate_to_previous_items(['item-yesterday-1', 'item-2', 'item-1'], json_response)


class ItemsUnImplementedEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model

    def setUp(self):
        self.client = Client()
        client_login(self.client)

    def test_item_post_unimplemented(self):
        sample = self.factory.create_item_sample(self.collection)
        response = self.client.post(
            f'/{STAC_BASE_V}/collections/{self.collection.name}/items',
            data=sample.get_json('post'),
            content_type="application/json"
        )
        self.assertStatusCode(405, response)


class ItemsCreateEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model

    def setUp(self):
        self.client = Client()
        client_login(self.client)

    def test_item_upsert_create(self):
        sample = self.factory.create_item_sample(self.collection)
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{sample.json["id"]}'
        response = self.client.put(
            path, data=sample.get_json('put'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.check_stac_item(sample.json, json_data, self.collection.name)

    def test_item_endpoint_create_only_required(self):
        sample = self.factory.create_item_sample(self.collection, required_only=True)
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{sample["name"]}'
        response = self.client.put(
            path, data=sample.get_json('put'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.assertLocationHeader(f'{path}', response)

        self.check_stac_item(sample.json, json_data, self.collection.name)

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(sample.json, json_data, self.collection.name)

    def test_item_upsert_create_non_existing_parent_collection_in_path(self):

        sample = self.factory.create_item_sample(self.collection, required_only=True)
        response = self.client.put(
            f'/{STAC_BASE_V}/collections/non-existing-collection/items/{sample.json["id"]}',
            data=sample.get_json('put'),
            content_type="application/json"
        )
        self.assertStatusCode(404, response)

    def test_item_atomic_upsert_create_500(self):
        sample = self.factory.create_item_sample(self.collection, sample='item-2')

        # the dataset to update does not exist yet
        with self.settings(DEBUG_PROPAGATE_API_EXCEPTIONS=True), disableLogger('stac_api.apps'):
            response = self.client.put(
                reverse('test-item-detail-http-500', args=[self.collection.name, sample['name']]),
                data=sample.get_json('put'),
                content_type='application/json'
            )
        self.assertStatusCode(500, response)
        self.assertEqual(response.json()['description'], "AttributeError('test exception')")

        # Make sure that the ressource has not been created
        response = self.client.get(
            reverse_version('item-detail', args=[self.collection.name, sample['name']])
        )
        self.assertStatusCode(404, response)

    def test_item_endpoint_create_invalid_data(self):
        data = self.factory.create_item_sample(self.collection,
                                               sample='item-invalid').get_json('put')
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{data["id"]}'
        response = self.client.put(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

        # Make sure that the item is not found in DB
        self.assertFalse(
            Item.objects.filter(name=data['id']).exists(),
            msg="Invalid item has been created in DB"
        )

    def test_item_endpoint_create_missing_datetime(self):
        data = self.factory.create_item_sample(
            self.collection,
            properties_datetime=None,
            properties_start_datetime=None,
            properties_end_datetime=None
        ).get_json('put')
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{data["id"]}'
        response = self.client.put(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

        # Make sure that the item is not found in DB
        self.assertFalse(
            Item.objects.filter(name=data['id']).exists(),
            msg="Invalid item has been created in DB"
        )


class ItemsUpdateEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample(db_create=True)
        cls.item = cls.factory.create_item_sample(
            cls.collection.model, sample='item-1', db_create=True
        )

    def setUp(self):
        self.client = Client()
        client_login(self.client)

    def test_item_endpoint_put(self):
        sample = self.factory.create_item_sample(
            self.collection.model, sample='item-2', name=self.item['name']
        )
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        response = self.client.put(
            path, data=sample.get_json('put'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(sample.json, json_data, self.collection["name"])

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(sample.json, json_data, self.collection["name"])

    def test_item_endpoint_put_extra_payload(self):
        sample = self.factory.create_item_sample(
            self.collection.model, sample='item-2', name=self.item['name'], extra_payload='invalid'
        )
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        response = self.client.put(
            path, data=sample.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(400, response)

    def test_item_endpoint_put_read_only_in_payload(self):
        data = self.factory.create_item_sample(
            self.collection.model, sample='item-2', name=self.item['name'], created=datetime.now()
        ).get_json('put')
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        response = self.client.put(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_put_update_to_datetime_range(self):
        sample = self.factory.create_item_sample(
            self.collection.model,
            sample='item-2',
            name=self.item['name'],
            properties={
                "start_datetime": "2020-10-18T00:00:00Z",
                "end_datetime": "2020-10-19T00:00:00Z",
            }
        )
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        response = self.client.put(
            path, data=sample.get_json('put'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(sample.json, json_data, self.collection["name"])

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(sample.json, json_data, self.collection["name"])
        self.assertNotIn('datetime', json_data['properties'].keys())
        self.assertNotIn('title', json_data['properties'].keys())

    def test_item_endpoint_put_remove_properties_title(self):
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        sample = self.factory.create_item_sample(
            self.collection.model,
            sample='item-2',
            name=self.item['name'],
            properties={
                "title": "item title",
                "start_datetime": "2020-10-18T00:00:00Z",
                "end_datetime": "2020-10-19T00:00:00Z",
            }
        )
        response = self.client.put(
            path, data=sample.get_json('put'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(self.item['name'], json_data['id'])
        self.assertIn("title", json_data['properties'].keys())

        sample = self.factory.create_item_sample(
            self.collection.model,
            sample='item-2',
            name=self.item['name'],
            properties={
                "title": None,
                "start_datetime": "2020-10-18T00:00:00Z",
                "end_datetime": "2020-10-19T00:00:00Z",
            }
        )
        response = self.client.put(
            path, data=sample.get_json('put'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(self.item['name'], json_data['id'])
        self.assertNotIn("title", json_data['properties'].keys())

    def test_item_endpoint_put_rename_item(self):
        sample = self.factory.create_item_sample(
            self.collection.model,
            sample='item-2',
            name=f'new-{self.item["name"]}',
        )
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        response = self.client.put(
            path, data=sample.get_json('put'), content_type="application/json"
        )
        json_data = response.json()
        self.assertStatusCode(400, response)
        self.assertEqual(json_data['description'], {'id': 'Renaming is not allowed'})

        # Make sure the original item was not updated
        self.assertTrue(
            Item.objects.all().filter(
                name=self.item["name"], collection__name=self.collection['name']
            ).exists(),
            msg="Original item doesn't exists anymore after trying to rename it"
        )

        # Make sure the rename item was not done
        self.assertFalse(
            Item.objects.all().filter(
                name=sample["name"], collection__name=self.collection['name']
            ).exists(),
            msg="Renamed item shouldn't exist"
        )

    def test_item_endpoint_patch(self):
        data = {"properties": {"title": "patched title"}}
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        response = self.client.patch(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(self.item['name'], json_data['id'])
        self.assertIn("title", json_data['properties'].keys())
        self.check_stac_item(data, json_data, self.collection["name"])

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(self.item['name'], json_data['id'])
        self.check_stac_item(data, json_data, self.collection["name"])
        self.assertIn("title", json_data['properties'].keys())

    def test_item_endpoint_patch_remove_properties_title(self):
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        # Check the data by reading, if there is a title on forehand
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(self.item['name'], json_data['id'])
        self.assertIn("title", json_data['properties'].keys())

        # Remove properties_title
        data = {"properties": {"title": None}}
        response = self.client.patch(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(self.item['name'], json_data['id'])
        self.assertNotIn("title", json_data['properties'].keys())

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(self.item['name'], json_data['id'])
        self.assertNotIn("title", json_data['properties'].keys())

    def test_item_endpoint_patch_extra_payload(self):
        data = {"crazy:stuff": "not allowed"}
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_patch_read_only_in_payload(self):
        data = {"created": utc_aware(datetime.utcnow())}
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_patch_invalid_datetimes(self):
        data = {"properties": {"datetime": "patched title",}}
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

        data = {"properties": {"start_datetime": "2020-10-28T13:05:10Z",}}
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_patch_rename_item(self):
        data = {
            "id": f'new-{self.item["name"]}',
        }
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{self.item["name"]}'
        response = self.client.patch(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(400, response)
        self.assertEqual(json_data['description'], {'id': 'Renaming is not allowed'})

        # Make sure the original item was not updated
        self.assertTrue(
            Item.objects.all().filter(
                name=self.item["name"], collection__name=self.collection['name']
            ).exists(),
            msg="Original item doesn't exists anymore after trying to rename it"
        )

        # Make sure the rename item was not done
        self.assertFalse(
            Item.objects.all().filter(name=data["id"],
                                      collection__name=self.collection['name']).exists(),
            msg="Renamed item shouldn't exist"
        )

    def test_item_atomic_upsert_update_500(self):
        sample = self.factory.create_item_sample(
            self.collection.model, sample='item-2', name=self.item['name']
        )
        # Make sure samples is different from actual data
        self.assertNotEqual(sample.attributes, self.item.attributes)

        # the dataset to update does not exist yet
        with self.settings(DEBUG_PROPAGATE_API_EXCEPTIONS=True), disableLogger('stac_api.apps'):
            # because we explicitely test a crash here we don't want to print a CRITICAL log on the
            # console therefore disable it.
            response = self.client.put(
                reverse(
                    'test-item-detail-http-500', args=[self.collection['name'], sample['name']]
                ),
                data=sample.get_json('put'),
                content_type='application/json'
            )
        self.assertStatusCode(500, response)
        self.assertEqual(response.json()['description'], "AttributeError('test exception')")

        # Make sure that the ressource has not been created
        response = self.client.get(
            reverse_version('item-detail', args=[self.collection['name'], sample['name']])
        )
        self.assertStatusCode(200, response)
        self.check_stac_item(self.item.json, response.json(), self.collection['name'])


class ItemRaceConditionTest(StacBaseTransactionTestCase):

    def setUp(self):
        self.username = 'user'
        self.password = 'dummy-password'
        get_user_model().objects.create_superuser(self.username, password=self.password)

    def test_item_upsert_race_condition(self):
        workers = 5
        status_201 = 0
        collection_sample = CollectionFactory().create_sample(sample='collection-2')
        item_sample = ItemFactory().create_sample(collection_sample.model, sample='item-1')

        def item_atomic_upsert_test(worker):
            # This method run on separate thread therefore it requires to create a new client and
            # to login it for each call.
            client = Client()
            client.login(username=self.username, password=self.password)
            return client.put(
                reverse_version(
                    'item-detail', args=[collection_sample['name'], item_sample['name']]
                ),
                data=item_sample.get_json('put'),
                content_type='application/json'
            )

        # We call the PUT item several times in parallel with the same data to make sure
        # that we don't have any race condition.
        responses, errors = self.run_parallel(workers, item_atomic_upsert_test)

        for worker, response in responses:
            if response.status_code == 201:
                status_201 += 1
            self.assertIn(
                response.status_code, [200, 201],
                msg=f'Unexpected response status code {response.status_code} for worker {worker}'
            )
            self.check_stac_item(item_sample.json, response.json(), collection_sample['name'])
        self.assertEqual(status_201, 1, msg="Not only one upsert did a create !")


class ItemsDeleteEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()

    @mock_s3_asset_file
    def setUp(self):
        self.client = Client()
        client_login(self.client)
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(self.collection, sample='item-1').model
        self.asset = self.factory.create_asset_sample(self.item, sample='asset-1').model

    def test_item_endpoint_delete_item(self):
        # Check that deleting, while assets are present, is not allowed
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.delete(path)
        self.assertStatusCode(400, response)
        self.assertEqual(response.json()['description'], ['Deleting Item with assets not allowed'])

        # delete asset first
        asset_path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{self.item.name}' \
             f'/assets/{self.asset.name}'
        response = self.client.delete(asset_path)
        self.assertStatusCode(200, response)

        # try item delete again
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.delete(path)
        self.assertStatusCode(200, response)

        # Check that is has really been deleted
        response = self.client.get(path)
        self.assertStatusCode(404, response)

        # Check that it is really not to be found in DB
        self.assertFalse(
            Item.objects.filter(name=self.item.name).exists(), msg="Deleted Item still found in DB"
        )

    def test_item_endpoint_delete_item_invalid_name(self):
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/unknown-item'
        response = self.client.delete(path)
        self.assertStatusCode(404, response)


class ItemsUnauthorizeEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.item = cls.factory.create_item_sample(cls.collection, sample='item-1').model

    def setUp(self):
        self.client = Client()

    def test_unauthorized_item_put_patch_delete(self):
        # make sure POST fails for anonymous user:
        sample = self.factory.create_item_sample(self.collection)

        # make sure PUT fails for anonymous user:
        sample = self.factory.create_item_sample(self.collection, name=self.item.name)
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.put(
            path, data=sample.get_json('put'), content_type="application/json"
        )
        self.assertStatusCode(401, response, msg="Unauthorized put was permitted.")

        # make sure PATCH fails for anonymous user:
        data = {"properties": {"title": "patched title"}}
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(401, response, msg="Unauthorized patch was permitted.")

        # make sure DELETE fails for anonymous user:
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.delete(path)
        self.assertStatusCode(401, response, msg="Unauthorized delete was permitted.")


class ItemsLinksEndpointTestCase(StacBaseTestCase):

    def setUp(self):
        self.client = Client()
        client_login(self.client)

    @classmethod
    def setUpTestData(cls) -> None:
        cls.factory = Factory()
        cls.collection_data = cls.factory.create_collection_sample(db_create=True)
        cls.collection = cast(Collection, cls.collection_data.model)
        cls.item_data: SampleData = cls.factory.create_item_sample(
            db_create=False, collection=cls.collection
        )
        cls.item = cast(Item, cls.item_data.model)
        return super().setUpTestData()

    def test_create_item_link_with_simple_link(self):
        data = self.item_data.get_json('put')

        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.put(path, data=data, content_type="application/json")

        self.assertEqual(response.status_code, 200)

        link = ItemLink.objects.last()
        assert link is not None
        self.assertEqual(link.rel, data['links'][0]['rel'])
        self.assertEqual(link.hreflang, None)

    def test_create_item_link_with_hreflang(self):
        data = self.item_data.get_json('put')
        data['links'] = [{
            'rel': 'more-info',
            'href': 'http://www.meteoschweiz.ch/',
            'title': 'A link to a german page',
            'type': 'text/html',
            'hreflang': "de"
        }]

        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.put(path, data=data, content_type="application/json")

        self.assertEqual(response.status_code, 200)

        link = ItemLink.objects.last()
        # Check for None with `assert` because `self.assertNotEqual` is not understood
        # by the type checker.
        assert link is not None
        self.assertEqual(link.hreflang, 'de')

    def test_read_item_with_hreflang(self):
        item_data: SampleData = self.factory.create_item_sample(
            sample='item-hreflang-links', db_create=False, collection=self.collection
        )
        item = cast(Item, item_data.model)

        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{item.name}'
        response = self.client.get(path, content_type="application/json")

        self.assertEqual(response.status_code, 200)

        json_data = response.json()
        self.assertIn('links', json_data)
        link_data = json_data['links']
        de_link = link_data[-2]
        fr_link = link_data[-1]
        self.assertEqual(de_link['hreflang'], 'de')
        self.assertEqual(fr_link['hreflang'], 'fr-CH')

    def test_update_item_link_with_invalid_hreflang(self):
        data = self.item_data.get_json('put')
        data['links'] = [{
            'rel': 'more-info',
            'href': 'http://www.meteoschweiz.ch/',
            'title': 'A link to a german page',
            'type': 'text/html',
            'hreflang': "fr/ch"
        }]

        path = f'/{STAC_BASE_V}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.put(path, data=data, content_type="application/json")

        self.assertEqual(response.status_code, 400)
        content = response.json()
        description = content['description'][0]
        self.assertIn('Unknown code', description)
        self.assertIn('Missing language', description)
