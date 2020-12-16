import logging
from datetime import datetime
from datetime import timedelta
from json import dumps
from json import loads
from pprint import pformat
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

from rest_framework.test import APIRequestFactory

from stac_api.models import Item
from stac_api.serializers import ItemSerializer
from stac_api.utils import fromisoformat
from stac_api.utils import isoformat
from stac_api.utils import utc_aware

import tests.database as db
from tests.base_test import StacBaseTestCase
from tests.utils import mock_request_from_response

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE
TEST_VALID_GEOMETRY = {
    "coordinates": [[
        [11.199955188064508, 45.30427347827474],
        [5.435800505341752, 45.34985402081985],
        [5.327213305905472, 48.19113734655604],
        [11.403439825339375, 48.14311756174606],
        [11.199955188064508, 45.30427347827474],
    ]],
    "type": "Polygon"
}


def to_dict(input_ordered_dict):
    return loads(dumps(input_ordered_dict))


class ItemsEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.factory = APIRequestFactory()
        self.client = Client()
        self.collections, self.items, self.assets = db.create_dummy_db_content(4, 4, 4)
        self.now = utc_aware(datetime.utcnow())
        self.yesterday = self.now - timedelta(days=1)
        item_yesterday = Item.objects.create(
            collection=self.collections[0],
            name='item-yesterday',
            properties_datetime=self.yesterday,
            properties_title="My Title",
        )
        db.create_item_links(item_yesterday)
        item_yesterday.full_clean()
        item_yesterday.save()
        item_now = Item.objects.create(
            collection=self.collections[0],
            name='item-now',
            properties_datetime=self.now,
            properties_title="My Title",
        )
        db.create_item_links(item_now)
        item_now.full_clean()
        item_now.save()
        item_range = Item.objects.create(
            collection=self.collections[0],
            name='item-range',
            properties_start_datetime=self.yesterday,
            properties_end_datetime=self.now,
            properties_title="My Title",
        )
        db.create_item_links(item_range)
        item_range.full_clean()
        item_range.save()
        self.collections[0].save()
        self.maxDiff = None  # pylint: disable=invalid-name
        self.username = 'SherlockHolmes'
        self.password = '221B_BakerStreet'
        self.superuser = get_user_model().objects.create_superuser(
            self.username, 'test_e_mail1234@some_fantasy_domainname.com', self.password
        )


class ItemsReadEndpointTestCase(ItemsEndpointTestCase):

    def test_items_endpoint_with_paging(self):
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items?limit=1"
        )
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))
        self.assertStatusCode(200, response)

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
            f"/{API_BASE}/collections/{self.collections[0].name}/items?"
            f"limit=100"
        )
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))
        self.assertStatusCode(200, response)

        self.assertEqual(7, len(json_data['features']), msg="Too many items found")

        # Check that pagination is present response
        self.assertTrue('links' in json_data, msg="'links' missing from response")
        for link in json_data['links']:
            self.assertNotIn(link['rel'], ['next', 'previous'], msg="should not have pagination")

    def test_single_item_endpoint(self):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        response = self.client.get(f"/{API_BASE}/collections/{collection_name}/items/{item_name}")
        json_data = response.json()
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))
        self.assertStatusCode(200, response)

        # The ETag change between each test call due to the created, updated time that are in the
        # hash computation of the ETag
        self.check_etag(None, response)

        # mock the request for creations of links
        request = mock_request_from_response(self.factory, response)

        # Check that the answer is equal to the initial data
        serializer = ItemSerializer(self.items[0][0], context={'request': request})
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            original_data, json_data, msg="Returned data does not match expected data"
        )
        # created and updated must exist and be a valid date
        date_fields = ['created', 'updated']
        for date_field in date_fields:
            self.assertTrue(
                fromisoformat(json_data['properties'][date_field]),
                msg=f"The field {date_field} has an invalid date"
            )

    def test_items_endpoint_datetime_query(self):
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?datetime={isoformat(self.now)}&limit=10"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(1, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-now', json_data['features'][0]['id'])

    def test_items_endpoint_datetime_range_query(self):
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?datetime={isoformat(self.yesterday)}/{isoformat(self.now)}&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(3, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-yesterday', json_data['features'][0]['id'])
        self.assertEqual('item-now', json_data['features'][1]['id'])

    def test_items_endpoint_datetime_open_end_range_query(self):
        # test open end query
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?datetime={isoformat(self.yesterday)}/..&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(3, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-yesterday', json_data['features'][0]['id'])
        self.assertEqual('item-now', json_data['features'][1]['id'])

    def test_items_endpoint_datetime_open_start_range_query(self):
        # test open start query
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?datetime=../{isoformat(self.yesterday)}&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(5, len(json_data['features']), msg="More than one item found")
        self.assertEqual('item-yesterday', json_data['features'][-1]['id'])

    def test_items_endpoint_datetime_invalid_range_query(self):
        # test open start and end query
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?datetime=../..&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid datetime
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?datetime=2019&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid start
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?datetime=2019/..&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid end
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?datetime=../2019&limit=100"
        )
        self.assertStatusCode(400, response)

        # invalid start and end
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?datetime=2019/2019&limit=100"
        )
        self.assertStatusCode(400, response)

    def test_items_endpoint_bbox_valid_query(self):
        # test bbox
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?bbox=5.96,45.82,10.49,47.81&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(7, len(json_data['features']), msg="More than one item found")
        self.assertEqual([5.644711, 46.775054, 7.602408, 49.014995],
                         json_data['features'][0]['bbox'])

    def test_items_endpoint_bbox_invalid_query(self):
        # test invalid bbox
        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?bbox=5.96,45.82,10.49,47.81,screw;&limit=100"
        )
        self.assertStatusCode(400, response)

        response = self.client.get(
            f"/{API_BASE}/collections/{self.collections[0].name}/items"
            f"?bbox=5.96,45.82,10.49,47.81,42,42&limit=100"
        )
        self.assertStatusCode(400, response)


class ItemsWriteEndpointTestCase(ItemsEndpointTestCase):

    def test_item_endpoint_post_only_required(self):
        data = {
            "id": "test",
            "geometry": TEST_VALID_GEOMETRY,
            "properties": {
                "datetime": "2020-10-18T00:00:00Z"
            }
        }
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items'
        self.client.login(username=self.username, password=self.password)
        response = self.client.post(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.assertTrue(response.has_header('Location'), msg="Location header is missing")
        self.assertEqual(
            urlparse(response['Location']).path, f'{path}/{data["id"]}', msg="Wrong location path"
        )
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

    def test_item_endpoint_post_full(self):
        data = {
            "id": "test",
            "geometry": TEST_VALID_GEOMETRY,
            "properties": {
                "datetime": "2020-10-18T00:00:00Z", "title": "My title"
            }
        }
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items'
        self.client.login(username=self.username, password=self.password)
        response = self.client.post(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.assertTrue(response.has_header('Location'), msg="Location header is missing")
        self.assertEqual(
            urlparse(response['Location']).path, f'{path}/{data["id"]}', msg="Wrong location path"
        )
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

    def test_item_endpoint_post_invalid_data(self):
        data = {
            "id": "test+invalid name",
            "geometry": TEST_VALID_GEOMETRY,
            "properties": {
                "title": "My title"
            }
        }
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items'
        self.client.login(username=self.username, password=self.password)
        response = self.client.post(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

        # Make sure that the item is not found in DB
        self.assertFalse(
            Item.objects.filter(name=data['id']).exists(),
            msg="Invalid item has been created in DB"
        )

    def test_item_endpoint_post_invalid_datetime(self):
        data = {"id": "test", "geometry": TEST_VALID_GEOMETRY, "properties": {"title": "My title"}}
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items'
        self.client.login(username=self.username, password=self.password)
        response = self.client.post(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

        # Make sure that the item is not found in DB
        self.assertFalse(
            Item.objects.filter(name=data['id']).exists(),
            msg="Invalid item has been created in DB"
        )

    def test_item_endpoint_put(self):
        data = {
            "id": self.items[0][0].name,
            "geometry": TEST_VALID_GEOMETRY,
            "properties": {
                "datetime": "2020-10-18T00:00:00Z",
                "title": "My title",
            }
        }
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{self.items[0][0].name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

    def test_item_endpoint_put_update_to_datetime_range(self):
        data = {
            "id": self.items[0][0].name,
            "geometry": TEST_VALID_GEOMETRY,
            "properties": {
                "start_datetime": "2020-10-18T00:00:00Z",
                "end_datetime": "2020-10-19T00:00:00Z",
            }
        }
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{self.items[0][0].name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

    def test_item_endpoint_put_remove_title(self):
        data = {
            "id": self.items[0][0].name,
            "geometry": TEST_VALID_GEOMETRY,
            "properties": {
                "datetime": "2020-10-18T00:00:00Z",
            }
        }
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{self.items[0][0].name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertNotIn(
            'title',
            json_data['properties'].keys(),
            msg=f"Title still in answer: properties={json_data['properties']}"
        )
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertNotIn('title', json_data['properties'].keys(), msg="Title still in answer")
        self.check_stac_item(data, json_data)

    def test_item_endpoint_put_rename_item(self):
        data = {
            "id": f'new-{self.items[0][0].name}',
            "geometry": TEST_VALID_GEOMETRY,
            "properties": {
                "datetime": "2020-10-18T00:00:00Z",
            }
        }
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{self.items[0][0].name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(data['id'], json_data['id'])
        self.assertNotIn(
            'title',
            json_data['properties'].keys(),
            msg=f"Title still in answer: properties={json_data['properties']}"
        )
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{data["id"]}'
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(data['id'], json_data['id'])
        self.assertNotIn('title', json_data['properties'].keys(), msg="Title still in answer")
        self.check_stac_item(data, json_data)

    def test_item_endpoint_patch(self):
        data = {"geometry": TEST_VALID_GEOMETRY, "properties": {"title": "patched title",}}
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{self.items[0][0].name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.patch(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(self.items[0][0].name, json_data['id'])
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(self.items[0][0].name, json_data['id'])
        self.check_stac_item(data, json_data)

    def test_item_endpoint_patch_invalid_datetimes(self):
        data = {"properties": {"datetime": "patched title",}}
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{self.items[0][0].name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

        data = {"properties": {"start_datetime": "2020-10-28T13:05:10Z",}}
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_item_endpoint_patch_rename_item(self):
        data = {
            "id": f'new-{self.items[0][0].name}',
        }
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{self.items[0][0].name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.patch(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(data['id'], json_data['id'])

        response = self.client.get(path)
        self.assertStatusCode(404, response)

        # Check the data by reading it back
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{data["id"]}'
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(data['id'], json_data['id'])

    def test_item_endpoint_delete_item(self):
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{self.items[0][0].name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.delete(path)
        self.assertStatusCode(200, response)

        # Check that is has really been deleted
        response = self.client.get(path)
        self.assertStatusCode(404, response)

        # Check that it is really not to be found in DB
        self.assertFalse(
            Item.objects.filter(name=self.items[0][0].name).exists(),
            msg="Deleted Item still found in DB"
        )

    def test_item_endpoint_delete_item_invalid_name(self):
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/non-existant-item'
        self.client.login(username=self.username, password=self.password)
        response = self.client.delete(path)
        self.assertStatusCode(404, response)

    def test_unauthorized_item_post_put_patch_delete(self):
        # make sure POST fails for anonymous user:
        data = {
            "id": "test",
            "geometry": TEST_VALID_GEOMETRY,
            "properties": {
                "datetime": "2020-10-18T00:00:00Z"
            }
        }
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items'
        response = self.client.post(path, data=data, content_type="application/json")
        self.assertEqual(401, response.status_code, msg="Unauthorized post was permitted.")

        # make sure PUT fails for anonymous user:
        data = {
            "id": self.items[0][0].name,
            "geometry": TEST_VALID_GEOMETRY,
            "properties": {
                "datetime": "2020-10-18T00:00:00Z",
                "title": "My title",
            }
        }
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{self.items[0][0].name}'
        response = self.client.put(path, data=data, content_type="application/json")
        self.assertEqual(401, response.status_code, msg="Unauthorized put was permitted.")

        # make sure PATCH fails for anonymous user:
        data = {"geometry": TEST_VALID_GEOMETRY, "properties": {"title": "patched title",}}
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{self.items[0][0].name}'
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertEqual(401, response.status_code, msg="Unauthorized patch was permitted.")

        # make sure DELETE fails for anonymous user:
        path = f'/{API_BASE}/collections/{self.collections[0].name}/items/{self.items[0][0].name}'
        response = self.client.delete(path)
        self.assertEqual(401, response.status_code, msg="Unauthorized delete was permitted.")
