from django.conf import settings
from django.test import Client
from django.test import TestCase
from collections import OrderedDict

from stac_api.serializers import CollectionSerializer

import tests.database as db

API_BASE = settings.API_BASE


class CollectionsEndpointTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.collection = db.create_collection()
        self.item, self.assets = db.create_item(self.collection)

        # transate to Python native:
        self.serializer = CollectionSerializer(self.collection)

    def test_collections_endpoint(self):
        collection_name = self.collection.collection_name
        response = self.client.get(f"/{API_BASE}collections?format=json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['collections'][0],
            self.serializer.data,
            msg="Returned data does not match expected data"
        )

    def test_single_collection_endpoint(self):
        collection_name = self.collection.collection_name
        response = self.client.get(f"/{API_BASE}collections/{collection_name}?format=json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data, self.serializer.data, msg="Returned data does not match expected data"
        )
