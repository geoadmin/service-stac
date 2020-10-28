import io
import logging
from collections import OrderedDict
from datetime import datetime
from pprint import pformat

from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework_gis.fields import GeoJsonDict

from django.test import TestCase

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import Keyword
from stac_api.models import Provider
from stac_api.models import get_default_stac_extensions
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import ItemSerializer

logger = logging.getLogger(__name__)


class SerializationTestCase(TestCase):

    def setUp(self):
        '''
        Prepare instances of keyword, link, provider and instance for testing.
        Adding the relationships among those by populating the ManyToMany fields
        '''
        # create keyword instance for testing
        self.keyword = Keyword.objects.create(name='test1')
        self.keyword.save()

        # create provider instance for testing
        self.provider = Provider.objects.create(
            name='provider1',
            description='description',
            roles=['licensor'],
            url='http://www.google.com'
        )
        self.provider.save()

        # create collection instance for testing
        self.collection = Collection.objects.create(
            id=1,
            crs=['http://www.google.com'],
            created=datetime.now(),
            updated=datetime.now(),
            description='desc',
            start_date=None,
            end_date=None,
            extent=[200000, 100000, 200001, 100005],
            collection_name='my collection',
            item_type='Feature',
            license='test',
            stac_extension=get_default_stac_extensions(),
            stac_version="0.9.0",
            summaries_eo_gsd=[10.1, 20.3, 30.44],
            summaries_proj=[1, 4, 22],
            geoadmin_variant=['blubb', 'blabb', 'blibb'],
            title='Test title'
        )
        self.collection.save()

        # create links instance for testing
        link = CollectionLink.objects.create(
            collection=self.collection,
            href='http://www.google.com',
            rel='rel',
            link_type='root',
            title='Test title'
        )
        link.save()

        # populate the ManyToMany relation fields
        self.collection.keywords.add(self.keyword)
        self.collection.providers.add(self.provider)

        # create item instance for testing
        self.item = Item.objects.create(
            collection=self.collection,
            item_name='item-for-test',
            properties_datetime='2020-10-28T13:05:10.473602Z',
            properties_eo_gsd=[10, 30],
            properties_title="My Title",
            stac_extensions=get_default_stac_extensions(),
            stac_version="0.9.0"
        )
        self.item.save()
        self._create_item_links()
        self._create_assets()

        # save the updated instances
        self.collection.save()
        self.keyword.save()
        self.provider.save()

    def _create_item_links(self):
        # create links instances for testing
        link_root = ItemLink.objects.create(
            item=self.item,
            href="https://data.geo.admin.ch/api/stac/v0.9/",
            rel='root',
            link_type='root',
            title='Root link'
        )
        link_self = ItemLink.objects.create(
            item=self.item,
            href=
            "https://data.geo.admin.ch/collections/ch.swisstopo.pixelkarte-farbe-pk50.noscale/items/smr50-263-2016",
            rel='self',
            link_type='self',
            title='Self link'
        )
        link_rel = ItemLink.objects.create(
            item=self.item,
            href=
            "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.pixelkarte-farbe-pk50.noscale",
            rel='rel',
            link_type='rel',
            title='Rel link'
        )
        link_root.save()
        link_self.save()
        link_rel.save()
        self.item.save()

    def _create_assets(self):
        asset = Asset.objects.create(
            collection=self.collection,
            feature=self.item,
            asset_name="my first asset",
            checksum_multihash="01205c3fd6978a7d0b051efaa4263a09",
            description="this an asset",
            eo_gsd=3.4,
            geoadmin_lang='fr',
            geoadmin_variant="kgrs",
            proj_epsq=2056,
            media_type="image/tiff; application=geotiff; profile=cloud-optimize",
            href=
            "https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk50.noscale/smr200-200-1-2019-2056-kgrs-10.tiff"
        )
        asset.save()
        self.item.save()

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
            'assets': {
                'my first asset': OrderedDict([
                    ('description', 'this an asset'),
                    ('title', ''),
                    (
                        'href',
                        'https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk50.noscale/smr200-200-1-2019-2056-kgrs-10.tiff'
                    ),
                    ('type', 'image/tiff; application=geotiff; profile=cloud-optimize'),
                    ('eo:gsd', 3.4),
                    ('proj:epsq', 2056),
                    ('geoadmin:variant', 'kgrs'),
                    ('geoadmin:lang', 'fr'),
                    ('checksum:multihash', '01205c3fd6978a7d0b051efaa4263a09')
                ])
            },
            'bbox': (2317000.0, 913000.0, 3057000.0, 1413000.0),
            'collection': 'my collection',
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
            'id': 'item-for-test',
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
            'properties': OrderedDict([
                ('datetime', '2020-10-28T13:05:10.473602Z'),
                ('title', 'My Title'),
                ('eo:gsd', [10, 30, 3.4])
            ]),
            'stac_extensions': [
                'eo',
                'proj',
                'view',
                'https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json'
            ],
            'stac_version': '0.9.0',
            'type': 'Feature'
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
