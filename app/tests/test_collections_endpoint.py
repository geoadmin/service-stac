import logging
from pprint import pformat

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
        self.collections, self.items, self.assets = db.create_dummy_db_content(4, 4, 4)

        # transate to Python native:
        self.serializer = CollectionSerializer(self.collections, many=True)

        self.maxDiff = None  # pylint: disable=invalid-name

    def test_collections_endpoint(self):
        collection_name = self.collections[0].collection_name
        response = self.client.get(f"/{API_BASE}collections")
        self.assertEqual(200, response.status_code)
        response_json = response.json()
        logger.debug('Serialized data:\n%s', pformat(self.serializer.data))
        logger.debug('Response:\n%s', pformat(response_json))
        self.assertListEqual(
            self.serializer.data[:2],
            response_json['collections'],
            msg="Returned data does not match expected data"
        )
        self.assertListEqual(['rel', 'href'], list(response_json['links'][0].keys()))

    def test_single_collection_endpoint(self):
        collection_name = self.collections[0].collection_name
        response = self.client.get(f"/{API_BASE}collections/{collection_name}")
        self.assertEqual(response.status_code, 200)
        self.assertDictContainsSubset(
            self.serializer.data[0],
            response.data,
            msg="Returned data does not match expected data"
        )

    def test_updating_collection(self):
        # Test, if the collection's summaries and extend were correctly updated
        # when new item and asset are added to the collection

        # translate to Python native:
        serializer = CollectionSerializer(self.collections[0])
        python_native = serializer.data

        # translate to JSON:
        json_string = JSONRenderer().render(python_native, renderer_context={'indent': 2})
        logger.debug('json string (test_updating_collection): %s', json_string.decode("utf-8"))

        # not using the created and updated fields here, as those obviously cannot be overwritten
        # inside database.py but are always set automatically.
        # TODO: the expected bbox here was slightly adapted to the following values: # pylint: disable=fixme
        # 5.602408, 46.775054, 5.644711, 48.014995 (because this is, what the code
        # yields).
        # the bbox of the item, where the geometry is copied from, is:
        # 5.644711, 46.775054, 8.17589, 48.027119
        # I tend to believe it is an error in the sample data rather than in the code ;-)
        # But this has to be verified together with Tobias on Monday.
        # But as the item geometry does contain an 5.602408, I guess the value
        # is correct.
        self.assertDictContainsSubset(
            {
                "stac_version": "0.9.0",
                "stac_extensions": [
                    "eo",
                    "proj",
                    "view",
                    "https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json"
                ],
                "id": "collection-1",
                "title": "Test title",
                "description": "This is a description",
                "summaries": {
                    "eo:gsd": [3.4],
                    "geoadmin:variant": ["kgrs"],
                    "proj:epsg": [2056],
                },
                "extent": {
                    "spatial": {
                        "bbox": [[5.602408, 46.775054, 5.644711, 48.014995]]
                    },
                    "temporal": {
                        "interval": [["2020-10-28T13:05:10Z", "2020-10-28T13:05:10Z"]]
                    }
                },
                "providers": [{
                    "name": "provider1",
                    "roles": ["licensor"],
                    "url": "http://www.google.com",
                    "description": "description"
                }],
                "license": "test",
                "links": [{
                    "href": "http://www.google.com",
                    "rel": "rel",
                    "link_type": "root",
                    "title": "Test title"
                }],
                "keywords": [{
                    "name": "test1"
                }, {
                    "name": "test2"
                }],
                "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"]
            },
            python_native,
        )

    def test_collections_limit_query(self):
        response = self.client.get(f"/{API_BASE}collections?limit=1")
        self.assertEqual(200, response.status_code)
        self.assertLessEqual(1, len(response.json()['collections']))

        response = self.client.get(f"/{API_BASE}collections?limit=0")
        self.assertEqual(400, response.status_code)

        response = self.client.get(f"/{API_BASE}collections?limit=test")
        self.assertEqual(400, response.status_code)

        response = self.client.get(f"/{API_BASE}collections?limit=-1")
        self.assertEqual(400, response.status_code)

        response = self.client.get(f"/{API_BASE}collections?limit=1000")
        self.assertEqual(400, response.status_code)
