import io
import logging
from collections import OrderedDict
from datetime import datetime
from datetime import timedelta
from pprint import pformat
from unittest.case import skip

from django.test import TestCase

from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework_gis.fields import GeoJsonDict

from stac_api.models import Item
from stac_api.serializers import AssetSerializer
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import ItemSerializer
from stac_api.utils import isoformat
from stac_api.utils import utc_aware

import tests.database as db

logger = logging.getLogger(__name__)


class SerializationTestCase(TestCase):

    def setUp(self):
        '''
        Prepare instances of keyword, link, provider and instance for testing.
        Adding the relationships among those by populating the ManyToMany fields
        '''
        self.collection = db.create_collection('collection-1')
        self.item = db.create_item(self.collection, 'item-1')
        self.asset = db.create_asset(self.collection, self.item, 'asset-1')
        self.maxDiff = None  # pylint: disable=invalid-name

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
        self.assertEqual(True, serializer.is_valid(), msg='Serializer data not valid.')
        # self.assertDictEqual(
        #     python_native,
        #     serializer.validated_data,
        #     msg='Back-translated data not equal initial data.'
        # )

    @skip("will be fixed with BGDIINF_SB-1409")
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
        expected = {
            'assets': {
                'asset-1': OrderedDict([
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
                ])
            },
            'bbox': (5.602408, 46.775054, 5.644711, 48.014995),
            'collection': 'collection-1',
            'geometry': GeoJsonDict([
                ('type', 'Polygon'),
                (
                    'coordinates',
                    [[
                        [5.644711, 46.775054],
                        [5.602408, 48.014995],
                        [5.602408, 48.014995],
                        [5.602408, 48.014995],
                        [5.644711, 46.775054],
                    ]]
                ),
            ]),
            'id': 'item-1',
            'links': [
                OrderedDict([
                    ('href', 'https://data.geo.admin.ch/api/stac/v0.9/'),
                    ('rel', 'root'),
                    ('link_type', 'root'),
                    ('title', 'Root link'),
                ]),
                OrderedDict([
                    (
                        'href',
                        'https://data.geo.admin.ch/collections/ch.swisstopo.pixelkarte-farbe-pk50.noscale/items/smr50-263-2016'
                    ),
                    ('rel', 'self'),
                    ('link_type', 'self'),
                    ('title', 'Self link'),
                ]),
                OrderedDict([
                    (
                        'href',
                        'https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.pixelkarte-farbe-pk50.noscale'
                    ),
                    ('rel', 'rel'),
                    ('link_type', 'rel'),
                    ('title', 'Rel link'),
                ])
            ],
            'properties': OrderedDict([
                ('datetime', '2020-10-28T13:05:10Z'),
                ('title', 'My Title'),
                ('eo:gsd', [3.4]),
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
        # yapf: enable
        self.assertDictEqual(expected, python_native)

        # Make sure that back translation is possible and valid, though the write is not yet
        # implemented.
        # back-translate to Python native:
        stream = io.BytesIO(json_string)
        python_native_back = JSONParser().parse(stream)

        # back-translate into fully populated Item instance:
        back_serializer = ItemSerializer(data=python_native_back)
        back_serializer.is_valid(raise_exception=True)
        logger.debug('back validated data:\n%s', pformat(back_serializer.validated_data))

    @skip("will be fixed with BGDIINF_SB-1409")
    def test_item_serialization_datetime_range(self):
        now = utc_aware(datetime.utcnow())
        yesterday = now - timedelta(days=1)
        item_range = Item.objects.create(
            collection=self.collection,
            item_name='item-range',
            properties_start_datetime=yesterday,
            properties_end_datetime=now,
            properties_eo_gsd=[10],
            properties_title="My Title",
        )
        db.create_item_links(item_range)
        item_range.save()

        # translate to Python native:
        serializer = ItemSerializer(item_range)
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
        expected = {
            'assets': {},
            'bbox': (5.96, 45.82, 10.49, 47.81),
            'collection': 'collection-1',
            'geometry': GeoJsonDict([
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
            'id': 'item-range',
            'links': [
                OrderedDict([
                    ('href', 'https://data.geo.admin.ch/api/stac/v0.9/'),
                    ('rel', 'root'),
                    ('link_type', 'root'),
                    ('title', 'Root link'),
                ]),
                OrderedDict([
                    (
                        'href',
                        'https://data.geo.admin.ch/collections/ch.swisstopo.pixelkarte-farbe-pk50.noscale/items/smr50-263-2016'
                    ),
                    ('rel', 'self'),
                    ('link_type', 'self'),
                    ('title', 'Self link'),
                ]),
                OrderedDict([
                    (
                        'href',
                        'https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.pixelkarte-farbe-pk50.noscale'
                    ),
                    ('rel', 'rel'),
                    ('link_type', 'rel'),
                    ('title', 'Rel link'),
                ])
            ],
            'properties': OrderedDict([
                ('start_datetime', isoformat(yesterday)),
                ('end_datetime', isoformat(now)),
                ('title', 'My Title'),
                ('eo:gsd', [10]),
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
        # yapf: enable
        self.assertDictEqual(expected, python_native)

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
        serializer = AssetSerializer(self.asset)
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
        back_serializer = AssetSerializer(instance=self.asset, data=python_native_back)
        back_serializer.is_valid(raise_exception=True)
        logger.debug('back validated data:\n%s', pformat(back_serializer.validated_data))
