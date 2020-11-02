import logging

from django.conf import settings
from django.test import Client
from django.test import TestCase

from rest_framework.renderers import JSONRenderer

from stac_api.serializers import CollectionSerializer

import tests.database as db

logger = logging.getLogger(__name__)

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

    def test_updating_collection(self):
        '''
        Test, if the collection's summaries and extend were correctly updated
        when new item and asset are added to the collection
        '''
        # translate to Python native:
        serializer = CollectionSerializer(self.collection)
        python_native = serializer.data

        # translate to JSON:
        json_string = JSONRenderer().render(python_native, renderer_context={'indent': 2})
        logger.debug('json string (test_updating_collection): %s', json_string.decode("utf-8"))

        # yapf: disable
        # not using the created and updated fields here, as those obviously cannot be overwritten
        # inside database.py but are always set automatically.
        self.assertDictContainsSubset({
            "stac_version": "0.9.0",
            "stac_extension": [
                "eo",
                "proj",
                "view",
                "https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json"
            ],
            "id": "ch.swisstopo.pixelkarte-farbe-pk200.noscale",
            "title": "Test title",
            "description": "This is a description",
            "summaries": {
                "eo:gsd": [
                3.4
                ],
                "geoadmin:variant": [
                "kgrs"
                ],
                "proj:epsg": [
                2056
                ]
            },
            "extent": {
                "spatial": {
                "bbox": [
                    [
                    None
                    ]
                ]
                },
                "temporal": {
                "interval": [
                    [
                    "2020-10-28T13:05:10.473602Z",
                    "2020-10-28T13:05:10.473602Z"
                    ]
                ]
                }
            },
            "providers": [
                {
                "name": "provider1",
                "roles": [
                    "licensor"
                ],
                "url": "http://www.google.com",
                "description": "description"
                }
            ],
            "license": "test",
            "links": [
                {
                "href": "http://www.google.com",
                "rel": "rel",
                "link_type": "root",
                "title": "Test title"
                }
            ],
            "keywords": [
                {
                "name": "test1"
                },
                {
                "name": "test2"
                }
            ],
            "crs": [
                "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
            ]
            }, python_native)
        # yapf: enable
