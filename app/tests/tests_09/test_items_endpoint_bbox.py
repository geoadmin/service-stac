import logging

from django.contrib.gis.geos.geometry import GEOSGeometry
from django.test import Client

from stac_api.models.general import BBOX_CH

from tests.tests_09.base_test import STAC_BASE_V
from tests.tests_09.base_test import StacBaseTestCase
from tests.tests_09.data_factory import Factory

logger = logging.getLogger(__name__)


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
                'item-paris',
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
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?bbox={ch_bbox}&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(5, len(json_data['features']), msg="More than one item found")

    def test_items_endpoint_bbox_invalid_query(self):
        # cannot converted to bbox
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?bbox=a,b,c,d&limit=100"
        )
        self.assertStatusCode(400, response)

        # wrong number of argument for bbox
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?bbox=0,0,2&limit=100"
        )
        self.assertStatusCode(400, response)

        # the geometry is not in the correct order (should be minx, miny,
        # maxx, maxy) but is still valid
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?bbox=1,1,0,0&limit=100"
        )
        self.assertStatusCode(200, response)

        # test invalid bbox
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?bbox=5.96,45.82,10.49,47.81,screw;&limit=100"
        )
        self.assertStatusCode(400, response)

        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?bbox=5.96,45.82,10.49,47.81,42,42&limit=100"
        )
        self.assertStatusCode(400, response)

    def test_items_endpoint_bbox_from_pseudo_point(self):
        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?bbox=5.96,45.82,5.97,45.83&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        nb_features_polygon = len(json_data['features'])

        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{self.collection.name}/items"
            f"?bbox=5.96,45.82,5.96,45.82&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        nb_features_point = len(json_data['features'])
        self.assertEqual(3, nb_features_point, msg="More than one item found")
        # do both queries return the same amount of items:
        self.assertEqual(nb_features_polygon, nb_features_point)
