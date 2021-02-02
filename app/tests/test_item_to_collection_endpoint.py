import logging

from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.test import Client

from tests.base_test import StacBaseTestCase
from tests.data_factory import Factory
from tests.utils import client_login

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


class OneItemSpatialTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.items = cls.factory.create_item_samples(['item-switzerland-west'],
                                                    cls.collection,
                                                    db_create=True)

    def setUp(self):
        self.client = Client()
        client_login(self.client)

    def test_single_item(self):
        collection_name = self.collection.name
        item_name = self.items[0].model.name
        response_item = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_name}"
        )
        response_item_json = response_item.json()
        response_collection = self.client.get(f"/{API_BASE}/collections/{collection_name}")
        response_collection_json = response_collection.json()

        bbox_collection = response_collection_json['extent']['spatial']['bbox'][0]
        bbox_items = response_item_json['bbox']

        self.assertEqual(bbox_items, bbox_collection)

    def test_no_items(self):
        collection_name = self.collection.name
        item_name = self.items[0].model.name
        # delete the item
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{item_name}'
        response = self.client.delete(path)
        self.assertStatusCode(200, response)

        response_collection = self.client.get(f"/{API_BASE}/collections/{collection_name}")
        response_collection_json = response_collection.json()

        bbox_collection = response_collection_json['extent']['spatial']['bbox'][0]

        self.assertEqual(bbox_collection, [])


class TwoItemsSpatialTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.items = cls.factory.create_item_samples(
            ['item-switzerland-west', 'item-switzerland-east'],
            cls.collection,
            name=['item-switzerland-west', 'item-switzerland-east'],
            db_create=True,
        )

    def setUp(self):
        self.client = Client()
        client_login(self.client)

    def test_two_item_endpoint(self):
        collection_name = self.collection.name
        item_west = self.items[0].model.name
        response_item_west = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_west}"
        )
        item_east = self.items[1].model.name
        response_item_east = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_east}"
        )

        response_collection = self.client.get(f"/{API_BASE}/collections/{collection_name}")
        response_collection_json = response_collection.json()

        bbox_collection = response_collection.json()['extent']['spatial']['bbox'][0]
        bbox_item_west = response_item_west.json()['bbox']
        bbox_item_east = response_item_east.json()['bbox']

        self.assertNotEqual(bbox_item_west, bbox_item_east, bbox_collection)

        polygon_west = Polygon.from_bbox(bbox_item_west)
        polygon_east = Polygon.from_bbox(bbox_item_east)
        union_polygon = Polygon.from_bbox(self._round_list(polygon_west.union(polygon_east).extent))

        collection_polygon = Polygon.from_bbox(self._round_list(bbox_collection))

        self.assertEqual(collection_polygon, union_polygon)

    def test_one_left_item(self):
        collection_name = self.collection.name
        item_west = self.items[0].model.name
        item_east = self.items[1].model.name

        # delete the eastern item
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{item_east}'
        response = self.client.delete(path)
        self.assertStatusCode(200, response)

        response_collection = self.client.get(f"/{API_BASE}/collections/{collection_name}")
        bbox_collection = response_collection.json()['extent']['spatial']['bbox'][0]

        response_item_west = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_west}"
        )
        bbox_item_west = response_item_west.json()['bbox']

        self.assertEqual(self._round_list(bbox_collection), self._round_list(bbox_item_west))

    def test_update_covering_item(self):
        collection_name = self.collection.name
        item_name = self.items[0].model.name
        sample = self.factory.create_item_sample(
            self.collection, sample='item-covers-switzerland', name=item_name
        )
        path = f'/{API_BASE}/collections/{self.collection.name}/items/{item_name}'
        response = self.client.put(
            path, data=sample.get_json('put'), content_type="application/json"
        )

        response_item = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_name}"
        )
        bbox_item = response_item.json()['bbox']

        response_collection = self.client.get(f"/{API_BASE}/collections/{collection_name}")
        bbox_collection = response_collection.json()['extent']['spatial']['bbox'][0]

        self.assertEqual(self._round_list(bbox_collection), self._round_list(bbox_item))

    def test_add_covering_item(self):
        collection_name = self.collection.name
        response_collection = self.client.get(f"/{API_BASE}/collections/{collection_name}")
        bbox_collection_ch = response_collection.json()['extent']['spatial']['bbox'][0]

        sample = self.factory.create_item_sample(
            self.collection, sample='item-covers-switzerland', db_create=True
        ).model
        response_collection = self.client.get(f"/{API_BASE}/collections/{collection_name}")
        bbox_collection_covers_ch = response_collection.json()['extent']['spatial']['bbox'][0]

        self.assertNotEqual(
            self._round_list(bbox_collection_ch), self._round_list(bbox_collection_covers_ch)
        )

        polygon_ch = Polygon.from_bbox(bbox_collection_ch)
        polygon_covers_ch = Polygon.from_bbox(bbox_collection_covers_ch)

        self.assertGreater(polygon_covers_ch.area, polygon_ch.area)

    def test_add_another_item(self):
        collection_name = self.collection.name
        response_collection = self.client.get(f"/{API_BASE}/collections/{collection_name}")
        bbox_collection_ch = response_collection.json()['extent']['spatial']['bbox'][0]

        sample = self.factory.create_item_sample(
            self.collection, sample='item-paris', db_create=True
        ).model
        response_collection = self.client.get(f"/{API_BASE}/collections/{collection_name}")
        bbox_collection_paris = response_collection.json()['extent']['spatial']['bbox'][0]

        self.assertNotEqual(
            self._round_list(bbox_collection_ch), self._round_list(bbox_collection_paris)
        )

        polygon_ch = Polygon.from_bbox(bbox_collection_ch)
        polygon_paris = Polygon.from_bbox(bbox_collection_paris)

        self.assertGreater(polygon_paris.area, polygon_ch.area)

    def _round_list(self, unrounded_list):
        '''round a list of numbers

        Args:
            unrounded_list: list(float)
        Returns:
            list
                A list of rounded numbers
        '''
        rounded_list = [round(i, 5) for i in unrounded_list]
        return rounded_list
