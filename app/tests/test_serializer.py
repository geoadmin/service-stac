# pylint: disable=too-many-lines

import io
import logging
from collections import OrderedDict
from datetime import datetime
from datetime import timedelta
from pprint import pformat

from django.conf import settings

from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIRequestFactory

from stac_api.models import Item
from stac_api.serializers import STAC_VERSION
from stac_api.serializers import AssetSerializer
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import ItemSerializer
from stac_api.utils import isoformat
from stac_api.utils import utc_aware

import tests.database as db
from tests.base_test import StacBaseTestCase

logger = logging.getLogger(__name__)
API_BASE = settings.API_BASE

geometry_json = OrderedDict([
    (
        "coordinates",
        [[
            [5.644711, 46.775054],
            [5.644711, 48.014995],
            [6.602408, 48.014995],
            [7.602408, 49.014995],
            [5.644711, 46.775054],
        ]]
    ),
    ("type", "Polygon"),
])


class CollectionSerializationTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        '''
        Prepare instances of keyword, link, provider and instance for testing.
        Adding the relationships among those by populating the ManyToMany fields
        '''
        self.factory = APIRequestFactory()
        self.collection_created = utc_aware(datetime.utcnow())
        self.collection = db.create_collection('collection-1')
        self.collection.full_clean()
        self.collection.save()
        self.item = db.create_item(self.collection, 'item-1')
        self.item.full_clean()
        self.item.save()
        self.asset = db.create_asset(self.item, 'asset-1')
        self.asset.full_clean()
        self.asset.save()
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_collection_serialization(self):
        collection_name = self.collection.name
        # mock a request needed for the serialization of links
        request = self.factory.get(f'{API_BASE}/collections/{collection_name}')

        # transate to Python native:
        serializer = CollectionSerializer(self.collection, context={'request': request})
        python_native = serializer.data
        logger.debug('python native:\n%s', pformat(python_native))

        # translate to JSON:
        content = JSONRenderer().render(python_native)
        logger.debug('json string: %s', content.decode("utf-8"))

        expected = {
            'created': isoformat(self.collection_created),
            'crs': ['http://www.opengis.net/def/crs/OGC/1.3/CRS84'],
            'description': 'This is a description',
            'extent':
                OrderedDict([
                    ('spatial', {
                        'bbox': [[5.644711, 46.775054, 7.602408, 49.014995]]
                    }),
                    ('temporal', {
                        'interval': [['2020-10-28T13:05:10Z', '2020-10-28T13:05:10Z']]
                    })
                ]),
            'id': collection_name,
            'itemType': 'Feature',
            'license': 'test',
            'links': [
                OrderedDict([
                    ('rel', 'self'),
                    ('href', f'http://testserver/api/stac/v0.9/collections/{collection_name}'),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', 'http://testserver/api/stac/v0.9/'),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    ('href', 'http://testserver/api/stac/v0.9/collections'),
                ]),
                OrderedDict([
                    ('rel', 'items'),
                    (
                        'href',
                        f'http://testserver/api/stac/v0.9/collections/{collection_name}/items'
                    ),
                ]),
                OrderedDict([
                    ('href', 'http://www.google.com'),
                    ('rel', 'dummy'),
                    ('type', 'dummy'),
                    ('title', 'Dummy link'),
                ])
            ],
            'providers': [
                OrderedDict([
                    ('name', 'provider1'),
                    ('roles', ['licensor']),
                    ('url', 'http://www.google.com'),
                    ('description', 'description'),
                ])
            ],
            'stac_extensions': [
                'eo',
                'proj',
                'view',
                'https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json'
            ],
            'stac_version': STAC_VERSION,
            'summaries': {
                'eo:gsd': [3.4],
                'geoadmin:variant': ['kgrs'],
                'proj:epsg': [2056],
            },
            'title': 'Test title',
            'updated': isoformat(self.collection_created)
        }
        self.check_stac_collection(expected, python_native)

    def test_collection_deserialization_create_only_required(self):
        data = OrderedDict([
            ("id", "test"),
            ("description", "This is a description for testing"),
            ("license", "proprietary"),
        ])

        # translate to Python native:
        serializer = CollectionSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(f'{API_BASE}/collections/{collection.name}')
        serializer = CollectionSerializer(collection, context={'request': request})
        python_native = serializer.data
        self.check_stac_collection(data, python_native)

    def test_collection_deserialization_create_full(self):
        data = OrderedDict([
            ("id", "test"),
            ("description", "This is a description for testing"),
            ("license", "proprietary"),
            ("title", "My title"),
            (
                "providers",
                [
                    OrderedDict([
                        ("name", "my-provider"),
                        ("description", "My provider description"),
                        ("roles", ["licensor"]),
                        ("url", "http://www.example.com"),
                    ])
                ]
            ),
            (
                "links",
                [
                    OrderedDict([
                        ('href', 'http://www.example.com'),
                        ('rel', 'example'),
                        ('title', 'This is an example link'),
                        ('type', 'example-type'),
                    ])
                ]
            ),
        ])

        # translate to Python native:
        serializer = CollectionSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(f'{API_BASE}/collections/{collection.name}')
        serializer = CollectionSerializer(collection, context={'request': request})
        python_native = serializer.data
        self.check_stac_collection(data, python_native)

    def test_collection_deserialization_create_provider_link_required(self):
        data = OrderedDict([
            ("id", "test"),
            ("description", "This is a description for testing"),
            ("license", "proprietary"),
            ("title", "My title"),
            ("providers", [OrderedDict([("name", "my-provider")])]),
            ("links", [OrderedDict([('href', 'http://www.example.com'), ('rel', 'example')])]),
        ])

        # translate to Python native:
        serializer = CollectionSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(f'{API_BASE}/collections/{collection.name}')
        serializer = CollectionSerializer(collection, context={'request': request})
        python_native = serializer.data
        self.check_stac_collection(data, python_native)

    def test_collection_deserialization_update_provider_link_required(self):
        data = OrderedDict([
            ("id", "test"),
            ("description", "This is a description for testing"),
            ("license", "proprietary"),
            ("title", "My title"),
            ("providers", [OrderedDict([("name", "my-provider")])]),
            ("links", [OrderedDict([('href', 'http://www.example.com'), ('rel', 'example')])]),
        ])

        # translate to Python native:
        serializer = CollectionSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()

        # Update some data
        data['description'] = 'New description'
        data['title'] = 'New Title'
        data['license'] = 'New license'
        data['providers'][0]['url'] = 'http://www.example.com'
        data['providers'][0]['roles'] = ['licensor']
        data['links'][0]['type'] = 'example'
        serializer = CollectionSerializer(collection, data=data)
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(f'{API_BASE}/collections/{collection.name}')
        serializer = CollectionSerializer(collection, context={'request': request})
        python_native = serializer.data
        self.check_stac_collection(data, python_native)

    def test_collection_deserialization_update_remove_add_provider_link(self):
        data = OrderedDict([
            ("id", "test"),
            ("description", "This is a description for testing"),
            ("license", "proprietary"),
            ("title", "My title"),
            ("providers", [OrderedDict([("name", "my-provider")])]),
            ("links", [OrderedDict([('href', 'http://www.example.com'), ('rel', 'example')])]),
        ])

        # translate to Python native:
        serializer = CollectionSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()

        # Remove and and new provider and link
        data['providers'][0]['name'] = 'new-provider'
        data['providers'][0]['url'] = 'http://www.example.com'
        data['providers'][0]['roles'] = ['licensor']
        data['links'][0] = OrderedDict([('href', 'http://www.new-example.com'),
                                        ('rel', 'new-example')])
        serializer = CollectionSerializer(collection, data=data)
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(f'{API_BASE}/collections/{collection.name}')
        serializer = CollectionSerializer(collection, context={'request': request})
        python_native = serializer.data
        self.check_stac_collection(data, python_native)

    def test_collection_deserialization_invalid_data(self):
        data = OrderedDict([
            ("id", "test/invalid name"),
            ("description", "This is a description for testing"),
            ("license", "proprietary"),
        ])

        # translate to Python native:
        serializer = CollectionSerializer(data=data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_collection_deserialization_invalid_link(self):
        data = OrderedDict([
            ("id", "test"),
            ("description", "This is a description for testing"),
            ("license", "proprietary"),
            ("links", [OrderedDict([('href', 'www.example.com'), ('rel', 'example')])]),
        ])

        # translate to Python native:
        serializer = CollectionSerializer(data=data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_collection_deserialization_invalid_provider(self):
        data = OrderedDict([
            ("id", "test"),
            ("description", "This is a description for testing"),
            ("license", "proprietary"),
            ("providers", [OrderedDict([("name", "my-provider"), ('roles', ['invalid-role'])])]),
        ])

        # translate to Python native:
        serializer = CollectionSerializer(data=data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)


class ItemSerializationTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        '''
        Prepare instances of keyword, link, provider and instance for testing.
        Adding the relationships among those by populating the ManyToMany fields
        '''
        self.factory = APIRequestFactory()
        self.collection_created = utc_aware(datetime.utcnow())
        self.collection = db.create_collection('collection-1')
        self.collection.full_clean()
        self.collection.save()
        self.item = db.create_item(self.collection, 'item-1')
        self.item.full_clean()
        self.item.save()
        self.asset = db.create_asset(self.item, 'asset-1')
        self.asset.full_clean()
        self.asset.save()
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_item_serialization(self):
        collection_name = self.collection.name
        item_name = self.item.name

        # mock a request needed for the serialization of links
        request = self.factory.get(f'{API_BASE}/collections/{collection_name}/items/{item_name}')

        # translate to Python native:
        serializer = ItemSerializer(self.item, context={'request': request})
        python_native = serializer.data

        logger.debug('python native:\n%s', pformat(python_native))

        # translate to JSON:
        json_string = JSONRenderer().render(python_native, renderer_context={'indent': 2})
        logger.debug('json string: %s', json_string.decode("utf-8"))

        self.assertSetEqual(
            set(['stac_version', 'id', 'bbox', 'geometry', 'type', 'properties', 'links',
                 'assets']).difference(python_native.keys()),
            set(),
            msg="These required fields by the STAC API spec are missing"
        )

        expected = {
            'assets': {
                'asset-1':
                    OrderedDict([
                        ('title', 'my-title'),
                        ('type', 'image/tiff; application=geotiff; '
                         'profile=cloud-optimize'),
                        ('href', f'http://testserver/{collection_name}/{item_name}/asset-1'),
                        ('description', 'this an asset'),
                        ('eo:gsd', 3.4),
                        ('proj:epsg', 2056),
                        ('geoadmin:variant', 'kgrs'),
                        ('geoadmin:lang', 'fr'),
                        ('checksum:multihash', '01205c3fd6978a7d0b051efaa4263a09'),
                    ])
            },
            'bbox': (5.644711, 46.775054, 7.602408, 49.014995),
            'collection': collection_name,
            'geometry':
                OrderedDict([
                    ('type', 'Polygon'),
                    (
                        'coordinates',
                        [[
                            [5.644711, 46.775054],
                            [5.644711, 48.014995],
                            [6.602408, 48.014995],
                            [7.602408, 49.014995],
                            [5.644711, 46.775054],
                        ]],
                    ),
                ]),
            'id': item_name,
            'links': [
                OrderedDict([
                    ('rel', 'self'),
                    (
                        'href',
                        f'http://testserver/api/stac/v0.9/collections/{collection_name}/items/{item_name}'
                    ),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', 'http://testserver/api/stac/v0.9/'),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    (
                        'href',
                        f'http://testserver/api/stac/v0.9/collections/{collection_name}/items'
                    ),
                ]),
                OrderedDict([
                    ('rel', 'collection'),
                    ('href', f'http://testserver/api/stac/v0.9/collections/{collection_name}'),
                ]),
                OrderedDict([
                    ('href', 'https://example.com'),
                    ('rel', 'dummy'),
                    ('type', 'dummy'),
                    ('title', 'Dummy link'),
                ])
            ],
            'properties':
                OrderedDict([
                    ('datetime', '2020-10-28T13:05:10Z'),
                    ('title', 'My Title'),
                ]),
            'stac_extensions': [
                'eo',
                'proj',
                'view',
                'https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json'
            ],
            'stac_version': STAC_VERSION,
            'type': 'Feature'
        }
        self.check_stac_item(expected, python_native)

    def test_item_serialization_datetime_range(self):
        now = utc_aware(datetime.utcnow())
        yesterday = now - timedelta(days=1)
        item_range = Item.objects.create(
            collection=self.collection,
            name='item-range',
            properties_start_datetime=yesterday,
            properties_end_datetime=now,
            properties_title="My Title",
        )
        db.create_item_links(item_range)
        item_range.full_clean()
        item_range.save()

        collection_name = self.collection.name
        item_name = item_range.name

        # mock a request needed for the serialization of links
        request = self.factory.get(f'{API_BASE}/collections/{collection_name}/items/{item_name}')

        # translate to Python native:
        serializer = ItemSerializer(item_range, context={'request': request})
        python_native = serializer.data

        logger.debug('serialized fields:\n%s', pformat(serializer.fields))
        logger.debug('python native:\n%s', pformat(python_native))

        # translate to JSON:
        json_string = JSONRenderer().render(python_native, renderer_context={'indent': 2})
        logger.debug('json string: %s', json_string.decode("utf-8"))

        self.assertSetEqual(
            set(['stac_version', 'id', 'bbox', 'geometry', 'type', 'properties', 'links',
                 'assets']).difference(python_native.keys()),
            set(),
            msg="These required fields by the STAC API spec are missing"
        )

        expected = {
            'assets': {},
            'bbox': (5.96, 45.82, 10.49, 47.81),
            'collection': collection_name,
            'geometry':
                OrderedDict([
                    ('type', 'Polygon'),
                    (
                        'coordinates',
                        [[
                            [5.96, 45.82],
                            [5.96, 47.81],
                            [10.49, 47.81],
                            [10.49, 45.82],
                            [5.96, 45.82],
                        ]]
                    ),
                ]),
            'id': item_name,
            'links': [
                OrderedDict([
                    ('rel', 'self'),
                    (
                        'href',
                        f'http://testserver/api/stac/v0.9/collections/{collection_name}/items/{item_name}',
                    ),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', 'http://testserver/api/stac/v0.9/'),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    (
                        'href',
                        f'http://testserver/api/stac/v0.9/collections/{collection_name}/items'
                    ),
                ]),
                OrderedDict([
                    ('rel', 'collection'),
                    (
                        'href',
                        f'http://testserver/api/stac/v0.9/collections/{collection_name}',
                    ),
                ]),
                OrderedDict([
                    ('href', 'https://example.com'),
                    ('rel', 'dummy'),
                    ('type', 'dummy'),
                    ('title', 'Dummy link'),
                ])
            ],
            'properties':
                OrderedDict([
                    ('start_datetime', isoformat(yesterday)),
                    ('end_datetime', isoformat(now)),
                    ('title', 'My Title'),
                ]),
            'stac_extensions': [
                'eo',
                'proj',
                'view',
                'https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json'
            ],
            'stac_version': STAC_VERSION,
            'type': 'Feature'
        }
        self.check_stac_item(expected, python_native)

    def test_item_deserialization_create_only_required(self):
        data = OrderedDict([
            ("collection", self.collection.name),
            ("id", "test"),
            ("geometry", geometry_json),
            ("properties", OrderedDict([("datetime", isoformat(utc_aware(datetime.utcnow())))])),
        ])

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(
            f'{API_BASE}/collections/{self.collection.name}/items/{item.name}'
        )
        serializer = ItemSerializer(item, context={'request': request})
        python_native = serializer.data
        self.check_stac_item(data, python_native)

    def test_item_deserialization_create_only_required_2(self):
        data = OrderedDict([
            ("collection", self.collection.name),
            ("id", "test"),
            ("geometry", geometry_json),
            (
                "properties",
                OrderedDict([
                    ("start_datetime", isoformat(utc_aware(datetime.utcnow()))),
                    ("end_datetime", isoformat(utc_aware(datetime.utcnow()))),
                ])
            ),
        ])

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(
            f'{API_BASE}/collections/{self.collection.name}/items/{item.name}'
        )
        serializer = ItemSerializer(item, context={'request': request})
        python_native = serializer.data
        self.check_stac_item(data, python_native)

    def test_item_deserialization_create_full(self):
        data = OrderedDict([
            ("collection", self.collection.name),
            ("id", "test"),
            ("geometry", geometry_json),
            (
                "properties",
                OrderedDict([
                    ("start_datetime", isoformat(utc_aware(datetime.utcnow()))),
                    ("end_datetime", isoformat(utc_aware(datetime.utcnow()))),
                    ("title", "This is a title"),
                ])
            ),
            ("links", [OrderedDict([('href', 'http://www.example.com'), ('rel', 'example')])]),
        ])

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(
            f'{API_BASE}/collections/{self.collection.name}/items/{item.name}'
        )
        serializer = ItemSerializer(item, context={'request': request})
        python_native = serializer.data
        self.check_stac_item(data, python_native)

    def test_item_deserialization_update_link_required(self):
        data = OrderedDict([
            ("collection", self.collection.name),
            ("id", "test"),
            ("geometry", geometry_json),
            (
                "properties",
                OrderedDict([
                    ("start_datetime", isoformat(utc_aware(datetime.utcnow()))),
                    ("end_datetime", isoformat(utc_aware(datetime.utcnow()))),
                    ("title", "This is a title"),
                ])
            ),
            ("links", [OrderedDict([('href', 'http://www.example.com'), ('rel', 'example')])]),
        ])

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # Update some data
        data['properties']['title'] = 'New Title'
        data['geometry']['coordinates'] = [[[5.602407647225925, 48.01499501585063],
                                            [8.175889890047533, 48.02711914887954],
                                            [8.158929420648244, 46.78690091679339],
                                            [5.644711296534027, 46.775053769032677],
                                            [5.602407647225925, 48.01499501585063]]]
        data['properties']['end_datetime'] = isoformat(utc_aware(datetime.utcnow()))
        data['links'][0]['type'] = 'example'
        serializer = ItemSerializer(item, data=data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(
            f'{API_BASE}/collections/{self.collection.name}/items/{item.name}'
        )
        serializer = ItemSerializer(item, context={'request': request})
        python_native = serializer.data
        self.check_stac_item(data, python_native)

    def test_item_deserialization_update_remove_link_update_datetime(self):
        data = OrderedDict([
            ("collection", self.collection.name),
            ("id", "test"),
            ("geometry", geometry_json),
            (
                "properties",
                OrderedDict([
                    ("start_datetime", isoformat(utc_aware(datetime.utcnow()))),
                    ("end_datetime", isoformat(utc_aware(datetime.utcnow()))),
                    ("title", "This is a title"),
                ])
            ),
            ("links", [OrderedDict([('href', 'http://www.example.com'), ('rel', 'example')])]),
        ])

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # Update some data
        data['properties']['datetime'] = isoformat(utc_aware(datetime.utcnow()))
        del data['properties']['start_datetime']
        del data['properties']['end_datetime']
        del data['links']
        serializer = ItemSerializer(item, data=data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(
            f'{API_BASE}/collections/{self.collection.name}/items/{item.name}'
        )
        serializer = ItemSerializer(item, context={'request': request})
        python_native = serializer.data
        self.check_stac_item(data, python_native)

    def test_item_deserialization_update_remove_title(self):
        data = OrderedDict([
            ("collection", self.collection.name),
            ("id", "test"),
            ("geometry", geometry_json),
            (
                "properties",
                OrderedDict([
                    ("start_datetime", isoformat(utc_aware(datetime.utcnow()))),
                    ("end_datetime", isoformat(utc_aware(datetime.utcnow()))),
                    ("title", "This is a title"),
                ])
            ),
        ])

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # Remove the optional title
        del data['properties']['title']
        serializer = ItemSerializer(item, data=data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(
            f'{API_BASE}/collections/{self.collection.name}/items/{item.name}'
        )
        serializer = ItemSerializer(item, context={'request': request})
        python_native = serializer.data
        self.assertNotIn('title', python_native['properties'].keys(), msg="Title was not removed")
        self.check_stac_item(data, python_native)

    def test_item_deserialization_missing_required(self):
        data = OrderedDict([
            ("collection", self.collection.name),
            ("id", "test"),
        ])

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_item_deserialization_invalid_data(self):
        data = OrderedDict([
            ("collection", self.collection.name),
            ("id", "test/invalid name"),
            ("geometry", geometry_json),
            ("properties", OrderedDict([("datetime", 'test')])),
        ])

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_item_deserialization_end_date_before_start_date(self):
        today = datetime.utcnow()
        yesterday = today - timedelta(days=1)
        data = OrderedDict([
            ("collection", self.collection.name),
            ("id", "test/invalid name"),
            ("geometry", geometry_json),
            (
                "properties",
                OrderedDict([
                    ("start_datetime", isoformat(utc_aware(today))),
                    ("end_datetime", isoformat(utc_aware(yesterday))),
                    ("title", "This is a title"),
                ])
            ),
        ])

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_item_deserialization_invalid_link(self):
        data = OrderedDict([
            ("collection", self.collection.name),
            ("id", "test/invalid name"),
            ("geometry", geometry_json),
            ("links", [OrderedDict([('href', 'www.example.com'), ('rel', 'example')])]),
        ])

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)


class AssetSerializationTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        '''
        Prepare instances of keyword, link, provider and instance for testing.
        Adding the relationships among those by populating the ManyToMany fields
        '''
        self.factory = APIRequestFactory()
        self.collection_created = utc_aware(datetime.utcnow())
        self.collection = db.create_collection('collection-1')
        self.collection.full_clean()
        self.collection.save()
        self.item = db.create_item(self.collection, 'item-1')
        self.item.full_clean()
        self.item.save()
        self.asset = db.create_asset(self.item, 'asset-1')
        self.asset.full_clean()
        self.asset.save()
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_serialization(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        # mock a request needed for the serialization of links
        request = self.factory.get(
            f'{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        )

        # translate to Python native:
        serializer = AssetSerializer(self.asset, context={'request': request})
        python_native = serializer.data

        logger.debug('serialized fields:\n%s', pformat(serializer.fields))
        logger.debug('python native:\n%s', pformat(python_native))

        # translate to JSON:
        json_string = JSONRenderer().render(python_native, renderer_context={'indent': 2})
        logger.debug('json string: %s', json_string.decode("utf-8"))

        expected = {
            'id': asset_name,
            'checksum:multihash': '01205c3fd6978a7d0b051efaa4263a09',
            'description': 'this an asset',
            'eo:gsd': 3.4,
            'geoadmin:lang': 'fr',
            'geoadmin:variant': 'kgrs',
            'href': f'http://testserver/{collection_name}/{item_name}/{asset_name}',
            'proj:epsg': 2056,
            'title': 'my-title',
            'type': 'image/tiff; application=geotiff; profile=cloud-optimize'
        }
        self.check_stac_asset(expected, python_native)

        # Make sure that back translation is possible and valid, though the write is not yet
        # implemented.
        # back-translate to Python native:
        stream = io.BytesIO(json_string)
        python_native_back = JSONParser().parse(stream)
        # hack to deal with the item property, as it is "write_only", it will not appear
        # in the mocked request's data. So we manually add it here:
        python_native_back["item"] = item_name

        # back-translate into fully populated Item instance:
        back_serializer = AssetSerializer(
            instance=self.asset, data=python_native_back, context={'request': request}
        )
        back_serializer.is_valid(raise_exception=True)
        logger.debug('back validated data:\n%s', pformat(back_serializer.validated_data))

    def test_asset_deserialization(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        data = {
            'id': "asset-2",
            'item': self.item.name,
            'checksum:multihash': '01205c3fd6978a7d0b051efaa4263a09',
            'description': 'this an asset',
            'eo:gsd': 3.4,
            'geoadmin:lang': 'fr',
            'geoadmin:variant': 'kgrs',
            'proj:epsg': 2056,
            'title': 'my-title',
            'type': 'image/tiff; application=geotiff; profile=cloud-optimize'
        }

        # translate to Python native:
        serializer = AssetSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        asset = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(
            f'{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset.name}'
        )
        serializer = AssetSerializer(asset, context={'request': request})
        python_native = serializer.data

        # ignoring item below, as it is a "write_only" field in the asset's serializer.
        # it will not be present in the mocked request's data.
        self.check_stac_asset(data, python_native, ignore=["item"])

    def test_asset_deserialization_required_fields_only(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        data = {
            'id': "asset-2",
            'item': self.item.name,
            'checksum:multihash': '01205c3fd6978a7d0b051efaa4263a09',
            'type': 'image/tiff; application=geotiff; profile=cloud-optimize'
        }

        # translate to Python native:
        serializer = AssetSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        asset = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        request = self.factory.get(
            f'{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset.name}'
        )
        serializer = AssetSerializer(asset, context={'request': request})
        python_native = serializer.data

        # ignoring item below, as it is a "write_only" field in the asset's serializer.
        # it will not be present in the mocked request's data.
        self.check_stac_asset(data, python_native, ignore=["item"])

    def test_asset_deserialization_invalid_id(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        data = {
            'id': "test/invalid name",
            'item': self.item.name,
            'checksum:multihash': '01205c3fd6978a7d0b051efaa4263a09',
            'description': 'this an asset',
            'eo:gsd': 3.4,
            'geoadmin:lang': 'fr',
            'geoadmin:variant': 'kgrs',
            'href':
                'https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk50.noscale/smr200-200-1-2019-2056-kgrs-10.tiff',
            'proj:epsg': 2056,
            'title': 'my-title',
            'type': 'image/tiff; application=geotiff; profile=cloud-optimize'
        }

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_asset_deserialization_invalid_proj_epsg(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        data = {
            'id': "asset-2",
            'item': self.item.name,
            'checksum:multihash': '01205c3fd6978a7d0b051efaa4263a09',
            'description': 'this an asset',
            'eo:gsd': 3.4,
            'geoadmin:lang': 'fr',
            'geoadmin:variant': 'kgrs',
            'href':
                'https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk50.noscale/smr200-200-1-2019-2056-kgrs-10.tiff',
            'proj:epsg': 2056.1,
            'title': 'my-title',
            'type': 'image/tiff; application=geotiff; profile=cloud-optimize'
        }

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_asset_deserialization_missing_required_item(self):
        collection_name = self.collection.name
        item_name = self.item.name
        asset_name = self.asset.name
        data = {
            'id': "asset-2",
            'checksum:multihash': '01205c3fd6978a7d0b051efaa4263a09',
            'description': 'this an asset',
            'eo:gsd': 3.4,
            'geoadmin:lang': 'fr',
            'geoadmin:variant': 'kgrs',
            'href':
                'https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk50.noscale/smr200-200-1-2019-2056-kgrs-10.tiff',
            'proj:epsg': 2056,
            'title': 'my-title',
            'type': 'image/tiff; application=geotiff; profile=cloud-optimize'
        }

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        with self.assertRaises(ValidationError):
            serializer.is_valid(raise_exception=True)
