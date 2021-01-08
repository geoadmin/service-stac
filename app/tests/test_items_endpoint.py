import logging
from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.contrib.gis.geos.geometry import GEOSGeometry
from django.test import Client

from stac_api.models import BBOX_CH
from stac_api.models import Item
from stac_api.utils import fromisoformat
from stac_api.utils import isoformat
from stac_api.utils import utc_aware

from tests.base_test import StacBaseTestCase
from tests.data_factory import Factory
from tests.utils import client_login

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


class ItemsReadEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.items = cls.factory.create_item_samples(2, cls.collection, db_create=True)

    def setUp(self):
        self.client = Client()

    def test_items_endpoint(self):
        response = self.client.get(f"/{API_BASE}/collections/{self.collection.name}/items")
        self.assertStatusCode(200, response)
        json_data = response.json()

        self.assertEqual(len(json_data['features']), 2, msg='Output should only have two features')

        self.check_stac_item(self.items[0].json, json_data['features'][0])
        self.check_stac_item(self.items[1].json, json_data['features'][1])

    def test_items_endpoint_with_limit(self):
        response = self.client.get(f"/{API_BASE}/collections/{self.collection.name}/items?limit=1")
        self.assertStatusCode(200, response)
        json_data = response.json()

        # Check that pagination is present
        self.assertTrue('links' in json_data, msg="'links' missing from response")

        self.assertEqual(len(json_data['features']), 1, msg='Output should only have one feature')

        self.check_stac_item(self.items[0].json, json_data['features'][0])

    def test_single_item_endpoint(self):
        collection_name = self.collection.name
        item_name = self.items[0].model.name
        response = self.client.get(f"/{API_BASE}/collections/{collection_name}/items/{item_name}")
        json_data = response.json()
        self.assertStatusCode(200, response)

        # The ETag change between each test call due to the created, updated time that are in the
        # hash computation of the ETag
        self.check_header_etag(None, response)

        self.check_stac_item(self.items[0].json, json_data)

        # created and updated must exist and be a valid date
        date_fields = ['created', 'updated']
        for date_field in date_fields:
            self.assertTrue(
                fromisoformat(json_data['properties'][date_field]),
                msg=f"The field {date_field} has an invalid date"
            )


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
            f"/{API_BASE}/collections/{self.collection.name}/items"
            f"?datetime={isoformat(self.now)}&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(1, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-now', json_data['features'][0]['id'])

    def test_items_endpoint_datetime_range_query(self):
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collection.name}/items"
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
            f"/{API_BASE}/collections/{self.collection.name}/items"
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
            f"/{API_BASE}/collections/{self.collection.name}/items"
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
            f"/{API_BASE}/collections/{self.collection.name}/items"
            f"?datetime=../..&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid datetime
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collection.name}/items"
            f"?datetime=2019&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid start
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collection.name}/items"
            f"?datetime=2019/..&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid end
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collection.name}/items"
            f"?datetime=../2019&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid start and end
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collection.name}/items"
            f"?datetime=2019/2019&limit=100"
        )
        self.assertStatusCode(400, response)


class ItemsBboxQueryEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model

        cls.items = cls.factory.create_item_samples(
            [
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

    def setUp(self):
        self.client = Client()

    def test_items_endpoint_bbox_valid_query(self):
        # test bbox
        ch_bbox = ','.join(map(str, GEOSGeometry(BBOX_CH).extent))
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collection.name}/items"
            f"?bbox={ch_bbox}&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(5, len(json_data['features']), msg="More than one item found")

    def test_items_endpoint_bbox_invalid_query(self):
        # test invalid bbox
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collection.name}/items"
            f"?bbox=5.96,45.82,10.49,47.81,screw;&limit=100"
        )
        self.assertStatusCode(400, response)

        response = self.client.get(
            f"/{API_BASE}/collections/{self.collection.name}/items"
            f"?bbox=5.96,45.82,10.49,47.81,42,42&limit=100"
        )
        self.assertStatusCode(400, response)


class ItemsWriteEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model

    def setUp(self):
        self.client = Client()
        client_login(self.client)

    def test_item_endpoint_post_only_required(self):
        data = self.factory.create_item_sample(self.collection, required_only=True).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items'
        response = self.client.post(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.check_header_location(f'{path}/{data["id"]}', response)

        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

    def test_item_endpoint_post_extra_payload(self):
        data = self.factory.create_item_sample(self.collection, extra_payload=True).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items'
        response = self.client.post(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_post_read_only_in_payload(self):
        data = self.factory.create_item_sample(self.collection, created=datetime.today()).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items'
        response = self.client.post(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_post_full(self):
        data = self.factory.create_item_sample(self.collection).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items'
        response = self.client.post(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.check_header_location(f'{path}/{data["id"]}', response)

        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

    def test_item_endpoint_post_invalid_data(self):
        data = self.factory.create_item_sample(self.collection, sample='item-invalid').json
        path = f'/{API_BASE}/collections/{self.collection.name}/items'
        response = self.client.post(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

        # Make sure that the item is not found in DB
        self.assertFalse(
            Item.objects.filter(name=data['id']).exists(),
            msg="Invalid item has been created in DB"
        )

    def test_item_endpoint_post_missing_datetime(self):
        data = self.factory.create_item_sample(
            self.collection,
            properties_datetime=None,
            properties_start_datetime=None,
            properties_end_datetime=None
        ).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items'
        response = self.client.post(path, data=data, content_type="application/json")
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
        cls.collection = cls.factory.create_collection_sample().model
        cls.item = cls.factory.create_item_sample(cls.collection, sample='item-1').model

    def setUp(self):
        self.client = Client()
        client_login(self.client)

    def test_item_endpoint_put(self):
        data = self.factory.create_item_sample(
            self.collection, sample='item-2', name=self.item.name
        ).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.put(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

    def test_item_endpoint_put_extra_payload(self):
        data = self.factory.create_item_sample(
            self.collection, sample='item-2', name=self.item.name, extra_payload='invalid'
        ).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.put(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_put_read_only_in_payload(self):
        data = self.factory.create_item_sample(
            self.collection, sample='item-2', name=self.item.name, created=datetime.now()
        ).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.put(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_put_update_to_datetime_range(self):
        data = self.factory.create_item_sample(
            self.collection,
            sample='item-2',
            name=self.item.name,
            properties={
                "start_datetime": "2020-10-18T00:00:00Z",
                "end_datetime": "2020-10-19T00:00:00Z",
            }
        ).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.put(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)
        self.assertNotIn('datetime', json_data['properties'].keys())
        self.assertNotIn('title', json_data['properties'].keys())

    def test_item_endpoint_put_rename_item(self):
        data = self.factory.create_item_sample(
            self.collection,
            sample='item-2',
            name=f'new-{self.item.name}',
        ).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.put(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(data['id'], json_data['id'])
        self.check_stac_item(data, json_data)

        response = self.client.get(path)
        self.assertStatusCode(404, response, msg="Renamed item still available on old name")

        # Check the data by reading it back
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{data["id"]}'
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(data['id'], json_data['id'])
        self.check_stac_item(data, json_data)

    def test_item_endpoint_patch(self):
        data = {"properties": {"title": "patched title"}}
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.patch(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(self.item.name, json_data['id'])
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(self.item.name, json_data['id'])
        self.check_stac_item(data, json_data)

    def test_item_endpoint_patch_extra_payload(self):
        data = {"crazy:stuff": "not allowed"}
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_patch_read_only_in_payload(self):
        data = {"created": utc_aware(datetime.utcnow())}
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_patch_invalid_datetimes(self):
        data = {"properties": {"datetime": "patched title",}}
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

        data = {"properties": {"start_datetime": "2020-10-28T13:05:10Z",}}
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_patch_rename_item(self):
        data = {
            "id": f'new-{self.item.name}',
        }
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.patch(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(data['id'], json_data['id'])

        response = self.client.get(path)
        self.assertStatusCode(404, response, msg="Renamed item still available on old name")

        # Check the data by reading it back
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{data["id"]}'
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(data['id'], json_data['id'])


class ItemsDeleteEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.item = cls.factory.create_item_sample(cls.collection, sample='item-1').model

    def setUp(self):
        self.client = Client()
        client_login(self.client)

    def test_item_endpoint_delete_item(self):
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
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
        path = f'/{API_BASE}/collections/{self.collection.name}/items/unknown-item'
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

    def test_unauthorized_item_post_put_patch_delete(self):
        # make sure POST fails for anonymous user:
        data = self.factory.create_item_sample(self.collection).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items'
        response = self.client.post(path, data=data, content_type="application/json")
        self.assertStatusCode(401, response, msg="Unauthorized post was permitted.")

        # make sure PUT fails for anonymous user:
        data = self.factory.create_item_sample(self.collection, name=self.item.name).json
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.put(path, data=data, content_type="application/json")
        self.assertStatusCode(401, response, msg="Unauthorized put was permitted.")

        # make sure PATCH fails for anonymous user:
        data = {"properties": {"title": "patched title"}}
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(401, response, msg="Unauthorized patch was permitted.")

        # make sure DELETE fails for anonymous user:
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{self.item.name}'
        response = self.client.delete(path)
        self.assertStatusCode(401, response, msg="Unauthorized delete was permitted.")
