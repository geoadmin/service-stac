import io
import logging
from collections import OrderedDict
from datetime import datetime
from datetime import timedelta
from pprint import pformat

from django.conf import settings

from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIRequestFactory

from stac_api.models import Item
from stac_api.serializers import AssetSerializer
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import ItemSerializer
from stac_api.utils import isoformat
from stac_api.utils import utc_aware

import tests.database as db
from tests.base_test import StacBaseTestCase

logger = logging.getLogger(__name__)
API_BASE = settings.API_BASE


class SerializationTestCase(StacBaseTestCase):

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
        collection_name = self.collection.collection_name
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
                    ('link_type', 'dummy'),
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
            'stac_version': '0.9.0',
            'summaries': {
                'eo:gsd': [3.4],
                'geoadmin:variant': ['kgrs'],
                'proj:epsg': [2056],
            },
            'title': 'Test title',
            'updated': isoformat(self.collection_created)
        }
        self.check_stac_collection(expected, python_native)

        # back-transate to Python native:
        stream = io.BytesIO(content)
        data = JSONParser().parse(stream)
        # back-translate into fully populated collection instance:
        serializer = CollectionSerializer(data=data, context={'request': request})
        self.assertEqual(True, serializer.is_valid(), msg='Serializer data not valid.')

    def test_item_serialization(self):
        collection_name = self.collection.collection_name
        item_name = self.item.item_name

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
                        (
                            'href',
                            'https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk50.noscale/smr200-200-1-2019-2056-kgrs-10.tiff'
                        ),
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
                    ('link_type', 'dummy'),
                    ('title', 'Dummy link'),
                ])
            ],
            'properties':
                OrderedDict([
                    ('datetime', '2020-10-28T13:05:10Z'),
                    ('title', 'My Title'),
                    ('eo:gsd', 3.4),
                ]),
            'stac_extensions': [
                'eo',
                'proj',
                'view',
                'https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json'
            ],
            'stac_version': '0.9.0',
            'type': 'Feature'
        }
        self.check_stac_item(expected, python_native)

        # Make sure that back translation is possible and valid, though the write is not yet
        # implemented.
        # back-translate to Python native:
        stream = io.BytesIO(json_string)
        python_native_back = JSONParser().parse(stream)

        # back-translate into fully populated Item instance:
        back_serializer = ItemSerializer(data=python_native_back)
        back_serializer.is_valid(raise_exception=True)
        logger.debug('back validated data:\n%s', pformat(back_serializer.validated_data))

    def test_item_serialization_datetime_range(self):
        now = utc_aware(datetime.utcnow())
        yesterday = now - timedelta(days=1)
        item_range = Item.objects.create(
            collection=self.collection,
            item_name='item-range',
            properties_start_datetime=yesterday,
            properties_end_datetime=now,
            properties_eo_gsd=float(10),
            properties_title="My Title",
        )
        db.create_item_links(item_range)
        item_range.full_clean()
        item_range.save()

        collection_name = self.collection.collection_name
        item_name = item_range.item_name

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
                    ('link_type', 'dummy'),
                    ('title', 'Dummy link'),
                ])
            ],
            'properties':
                OrderedDict([
                    ('start_datetime', isoformat(yesterday)),
                    ('end_datetime', isoformat(now)),
                    ('title', 'My Title'),
                    ('eo:gsd', float(10)),
                ]),
            'stac_extensions': [
                'eo',
                'proj',
                'view',
                'https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json'
            ],
            'stac_version': '0.9.0',
            'type': 'Feature'
        }
        self.check_stac_item(expected, python_native)

        # Make sure that back translation is possible and valid, though the write is not yet
        # implemented.
        # back-translate to Python native:
        stream = io.BytesIO(json_string)
        python_native_back = JSONParser().parse(stream)

        # back-translate into fully populated Item instance:
        back_serializer = ItemSerializer(data=python_native_back)
        back_serializer.is_valid(raise_exception=True)
        logger.debug('back validated data:\n%s', pformat(back_serializer.validated_data))

    def test_asset_serialization(self):
        collection_name = self.collection.collection_name
        item_name = self.item.item_name
        asset_name = self.asset.asset_name
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
            'asset_name': asset_name,
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
        self.check_stac_asset(expected, python_native)

        # Make sure that back translation is possible and valid, though the write is not yet
        # implemented.
        # back-translate to Python native:
        stream = io.BytesIO(json_string)
        python_native_back = JSONParser().parse(stream)

        # back-translate into fully populated Item instance:
        back_serializer = AssetSerializer(
            instance=self.asset, data=python_native_back, context={'request': request}
        )
        back_serializer.is_valid(raise_exception=True)
        logger.debug('back validated data:\n%s', pformat(back_serializer.validated_data))
