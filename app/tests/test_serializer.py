import io
import logging
from collections import OrderedDict
from pprint import pformat

from django.test import TestCase

from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework_gis.fields import GeoJsonDict

from stac_api.serializers import AssetSerializer
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import ItemSerializer

import tests.database as db

logger = logging.getLogger(__name__)


class SerializationTestCase(TestCase):

    def setUp(self):
        '''
        Prepare instances of keyword, link, provider and instance for testing.
        Adding the relationships among those by populating the ManyToMany fields
        '''
        self.collection = db.create_collection()
        self.item, self.assets = db.create_item(self.collection)

    def test_collection_serialization(self):

        # transate to Python native:
        serializer = CollectionSerializer(self.collection)
        python_native = serializer.data

        # translate to JSON:
        content = JSONRenderer().render(python_native)

        # back-transate to Python native:
        stream = io.BytesIO(content)
        data = JSONParser().parse(stream)

        # back-translate into fully populated collection instance:
        serializer = CollectionSerializer(data=data)

        self.assertEqual(serializer.is_valid(), True, msg='Serializer data not valid.')
        self.assertEqual(python_native, data, msg='Back-translated data not equal initial data.')

    def test_item_serialization(self):

        # translate to Python native:
        serializer = ItemSerializer(self.item)
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

        # yapf: disable
        self.assertDictContainsSubset({
            'id': 'item-for-test',
            'collection': 'ch.swisstopo.pixelkarte-farbe-pk200.noscale',
            'type': 'Feature',
            'stac_version': '0.9.0',
            'geometry': GeoJsonDict([
                ('type', 'MultiPolygon'),
                ('coordinates', [[[
                    [2317000.0, 913000.0, 0.0],
                    [3057000.0, 913000.0, 0.0],
                    [3057000.0, 1413000.0, 0.0],
                    [2317000.0, 1413000.0, 0.0],
                    [2317000.0, 913000.0, 0.0]
                ]]])
            ]),
            'bbox': (2317000.0, 913000.0, 3057000.0, 1413000.0),
            'properties': OrderedDict([
                ('datetime', '2020-10-28T13:05:10.473602Z'),
                ('title', 'My Title'),
                ('eo:gsd', [3.4])
            ]),
            'stac_extensions': [
                'eo',
                'proj',
                'view',
                'https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json'
            ],
            'links': [
                OrderedDict([
                    ('href', 'https://data.geo.admin.ch/api/stac/v0.9/'),
                    ('rel', 'root'),
                    ('link_type', 'root'),
                    ('title', 'Root link')
                ]),
                OrderedDict([
                    (
                        'href',
                        'https://data.geo.admin.ch/collections/ch.swisstopo.pixelkarte-farbe-pk50.noscale/items/smr50-263-2016'
                    ),
                    ('rel', 'self'),
                    ('link_type', 'self'),
                    ('title', 'Self link')
                ]),
                OrderedDict([
                    (
                        'href',
                        'https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.pixelkarte-farbe-pk50.noscale'
                    ),
                    ('rel', 'rel'),
                    ('link_type', 'rel'),
                    ('title', 'Rel link')
                ])
            ],
            'assets': {
                'my first asset': OrderedDict([
                    ('title', 'my-title'),
                    ('type', 'image/tiff; application=geotiff; profile=cloud-optimize'),
                    (
                        'href',
                        'https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk50.noscale/smr200-200-1-2019-2056-kgrs-10.tiff'
                    ),
                    ('description', 'this an asset'),
                    ('eo:gsd', 3.4),
                    ('proj:epsg', 2056),
                    ('geoadmin:variant', 'kgrs'),
                    ('geoadmin:lang', 'fr'),
                    ('checksum:multihash', '01205c3fd6978a7d0b051efaa4263a09')
                ])
            },
        }, python_native)
        # yapf: enable

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

        # translate to Python native:
        serializer = AssetSerializer(self.assets[0])
        python_native = serializer.data

        logger.debug('serialized fields:\n%s', pformat(serializer.fields))
        logger.debug('python native:\n%s', pformat(python_native))

        # translate to JSON:
        json_string = JSONRenderer().render(python_native, renderer_context={'indent': 2})
        logger.debug('json string: %s', json_string.decode("utf-8"))

        self.assertDictContainsSubset(
            OrderedDict([
                ('title', 'my-title'),
                ('type', 'image/tiff; application=geotiff; profile=cloud-optimize'),
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
            ]),
            python_native
        )

        # Make sure that back translation is possible and valid, though the write is not yet
        # implemented.
        # back-translate to Python native:
        stream = io.BytesIO(json_string)
        python_native_back = JSONParser().parse(stream)

        # back-translate into fully populated Item instance:
        back_serializer = AssetSerializer(instance=self.assets[0], data=python_native_back)
        back_serializer.is_valid(raise_exception=True)
        logger.debug('back validated data:\n%s', pformat(back_serializer.validated_data))
