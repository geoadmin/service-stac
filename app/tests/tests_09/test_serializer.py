# pylint: disable=too-many-lines

import logging
from collections import OrderedDict
from datetime import datetime
from datetime import timedelta
from pprint import pformat

from django.urls import resolve

from rest_framework import serializers
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIRequestFactory

from stac_api.serializers.collection import CollectionSerializer
from stac_api.serializers.item import AssetSerializer
from stac_api.serializers.item import ItemSerializer
from stac_api.utils import get_asset_path
from stac_api.utils import get_link
from stac_api.utils import isoformat
from stac_api.utils import utc_aware

from tests.tests_09.base_test import STAC_BASE_V
from tests.tests_09.base_test import STAC_VERSION
from tests.tests_09.base_test import StacBaseTestCase
from tests.tests_09.base_test import StacBaseTransactionTestCase
from tests.tests_09.data_factory import Factory
from tests.tests_09.utils import calculate_extent
from tests.utils import MockS3PerClassMixin
from tests.utils import MockS3PerTestMixin

logger = logging.getLogger(__name__)

api_request_mocker = APIRequestFactory()


def request_with_resolver(path):
    request = api_request_mocker.get(path)
    request.resolver_match = resolve(path)
    return request


# Here we need to use TransactionTestCase due to the pgtrigger, in a normal
# test case we cannot test effect of pgtrigger.
class CollectionSerializationTestCase(MockS3PerTestMixin, StacBaseTransactionTestCase):

    def setUp(self):
        super().setUp()
        self.data_factory = Factory()
        self.collection_created_after = utc_aware(datetime.now())
        self.collection = self.data_factory.create_collection_sample(db_create=True)
        self.item = self.data_factory.create_item_sample(
            collection=self.collection.model, db_create=True
        )
        self.asset = self.data_factory.create_asset_sample(item=self.item.model, db_create=True)
        calculate_extent()
        self.collection.model.refresh_from_db()
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_collection_serialization(self):
        collection_name = self.collection.model.name
        # mock a request needed for the serialization of links
        context = {
            'request': request_with_resolver(f'/{STAC_BASE_V}/collections/{collection_name}')
        }

        # transate to Python native:
        serializer = CollectionSerializer(self.collection.model, context=context)
        python_native = serializer.data
        logger.debug('python native:\n%s', pformat(python_native))

        # translate to JSON:
        content = JSONRenderer().render(python_native)
        logger.debug('json string: %s', content.decode("utf-8"))

        expected = self.collection.get_json('serialize')
        expected.update({
            'created': isoformat(self.collection_created_after),
            'crs': ['http://www.opengis.net/def/crs/OGC/1.3/CRS84'],
            'extent': {
                'spatial': {
                    'bbox': [[5.644711, 46.775054, 7.602408, 49.014995]]
                },
                'temporal': {
                    'interval': [['2020-10-28T13:05:10Z', '2020-10-28T13:05:10Z']]
                }
            },
            'itemType': 'Feature',
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
                    ('href', 'http://testserver/api/stac/v0.9/'),
                ]),
                OrderedDict([
                    ('rel', 'items'),
                    (
                        'href',
                        f'http://testserver/api/stac/v0.9/collections/{collection_name}/items'
                    ),
                ]),
                OrderedDict([
                    ('href', 'https://www.example.com/described-by'),
                    ('rel', 'describedBy'),
                    ('type', 'description'),
                    ('title', 'This is an extra collection link'),
                ])
            ],
            'providers': [
                {
                    'name': 'provider-1',
                    'roles': ['licensor', 'producer'],
                    'description': 'This is a full description of the provider',
                    'url': 'https://www.provider.com'
                },
                {
                    'name': 'provider-2',
                    'roles': ['licensor'],
                    'description': 'This is a full description of a second provider',
                    'url': 'https://www.provider.com/provider-2'
                },
                {
                    'name': 'provider-3',
                },
            ],
            'stac_version': STAC_VERSION,
            'summaries': {
                'eo:gsd': [3.4],
                'geoadmin:variant': ['kgrs'],
                'proj:epsg': [2056],
            },
            'updated': isoformat(self.collection_created_after)
        })
        self.check_stac_collection(expected, python_native)


class EmptyCollectionSerializationTestCase(StacBaseTransactionTestCase):

    def setUp(self):
        self.data_factory = Factory()
        self.collection_created_after = utc_aware(datetime.now())
        self.collection = self.data_factory.create_collection_sample(db_create=True)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_empty_collection_serialization(self):
        collection_name = self.collection.model.name
        # mock a request needed for the serialization of links
        context = {
            'request': request_with_resolver(f'/{STAC_BASE_V}/collections/{collection_name}')
        }

        # transate to Python native:
        serializer = CollectionSerializer(self.collection.model, context=context)
        python_native = serializer.data
        logger.debug('python native:\n%s', pformat(python_native))

        # translate to JSON:
        content = JSONRenderer().render(python_native)
        logger.debug('json string: %s', content.decode("utf-8"))

        expected = self.collection.get_json('serialize')
        expected.update({
            'created': isoformat(self.collection_created_after),
            'crs': ['http://www.opengis.net/def/crs/OGC/1.3/CRS84'],
            'extent': {
                'spatial': {
                    'bbox': [[]]
                }, 'temporal': {
                    'interval': [[None, None]]
                }
            },
            'itemType': 'Feature',
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
                    ('href', 'http://testserver/api/stac/v0.9/'),
                ]),
                OrderedDict([
                    ('rel', 'items'),
                    (
                        'href',
                        f'http://testserver/api/stac/v0.9/collections/{collection_name}/items'
                    ),
                ]),
                OrderedDict([
                    ('href', 'https://www.example.com/described-by'),
                    ('rel', 'describedBy'),
                    ('type', 'description'),
                    ('title', 'This is an extra collection link'),
                ])
            ],
            'providers': [
                {
                    'name': 'provider-1',
                    'roles': ['licensor', 'producer'],
                    'description': 'This is a full description of the provider',
                    'url': 'https://www.provider.com'
                },
                {
                    'name': 'provider-2',
                    'roles': ['licensor'],
                    'description': 'This is a full description of a second provider',
                    'url': 'https://www.provider.com/provider-2'
                },
                {
                    'name': 'provider-3',
                },
            ],
            'stac_version': STAC_VERSION,
            'summaries': {},
            'updated': isoformat(self.collection_created_after)
        })
        self.check_stac_collection(expected, python_native)


class CollectionDeserializationTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.data_factory = Factory()

    def setUp(self):  # pylint: disable=invalid-name
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_collection_deserialization_create_only_required(self):
        sample = self.data_factory.create_collection_sample(required_only=True)
        serializer = CollectionSerializer(data=sample.get_json('deserialize'))
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()

        # mock a request needed for the serialization of links
        context = {
            'request': request_with_resolver(f'/{STAC_BASE_V}/collections/{collection.name}')
        }
        serializer = CollectionSerializer(collection, context=context)
        python_native = serializer.data
        self.check_stac_collection(sample.json, python_native)

    def test_collection_deserialization_create_full(self):
        sample = self.data_factory.create_collection_sample()
        serializer = CollectionSerializer(data=sample.get_json('deserialize'))
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        context = {
            'request': request_with_resolver(f'/{STAC_BASE_V}/collections/{collection.name}')
        }
        serializer = CollectionSerializer(collection, context=context)
        python_native = serializer.data
        self.check_stac_collection(sample.json, python_native)

    def test_collection_deserialization_update_existing(self):
        # Create a collection
        collection = self.data_factory.create_collection_sample(sample='collection-1').model

        # Get a new samples based on another sample
        sample = self.data_factory.create_collection_sample(
            sample='collection-4', name=collection.name
        )
        context = {
            'request': request_with_resolver(f'/{STAC_BASE_V}/collections/{collection.name}')
        }
        serializer = CollectionSerializer(
            collection, data=sample.get_json('deserialize'), context=context
        )
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        serializer = CollectionSerializer(collection, context=context)
        python_native = serializer.data
        self.check_stac_collection(sample.json, python_native)

        self.assertNotIn('providers', python_native, msg='Providers have not been removed')
        self.assertIn('links', python_native, msg='Generated links missing')
        self.assertIsNone(
            get_link(python_native['links'], 'describedBy'),
            msg='User link describedBy have not been removed'
        )

    def test_collection_deserialization_invalid_data(self):
        data = self.data_factory.create_collection_sample(sample='collection-invalid'
                                                         ).get_json('deserialize')

        # translate to Python native:
        serializer = CollectionSerializer(data=data)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_collection_deserialization_invalid_link(self):
        data = self.data_factory.create_collection_sample(sample='collection-invalid-links'
                                                         ).get_json('deserialize')

        # translate to Python native:
        serializer = CollectionSerializer(data=data)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_collection_deserialization_invalid_provider(self):
        data = self.data_factory.create_collection_sample(sample='collection-invalid-providers'
                                                         ).get_json('deserialize')

        # translate to Python native:
        serializer = CollectionSerializer(data=data)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class ItemSerializationTestCase(MockS3PerTestMixin, StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        super().setUp()
        self.data_factory = Factory()
        self.collection = self.data_factory.create_collection_sample(db_create=True)
        self.item = self.data_factory.create_item_sample(
            collection=self.collection.model, db_create=True
        )
        self.asset = self.data_factory.create_asset_sample(item=self.item.model, db_create=True)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_item_serialization(self):

        context = {
            'request':
                request_with_resolver(
                    f'''/{STAC_BASE_V}/collections/{self.collection["name"]}
/items/{self.item["name"]}'''
                )
        }
        serializer = ItemSerializer(self.item.model, context=context)
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

        collection_name = self.collection.model.name
        expected_asset = self.asset.json
        expected_asset.pop('id')
        expected = self.item.json
        expected.update({
            'assets': {
                self.asset['name']: expected_asset
            },
            'bbox': (5.644711, 46.775054, 7.602408, 49.014995),
            'stac_version': STAC_VERSION,
            'type': 'Feature'
        })
        self.check_stac_item(expected, python_native, collection_name)

    def test_item_serialization_datetime_range(self):
        sample = self.data_factory.create_item_sample(
            collection=self.collection.model, sample='item-2'
        )
        # translate to Python native:
        context = {
            'request':
                request_with_resolver(
                    f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{sample["name"]}'
                )
        }
        serializer = ItemSerializer(sample.model, context=context)
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
        self.check_stac_item(sample.json, python_native, self.collection["name"])


class ItemDeserializationTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):  # pylint: disable=invalid-name
        cls.data_factory = Factory()
        cls.collection = cls.data_factory.create_collection_sample(db_create=True)

    def setUp(self):  # pylint: disable=invalid-name
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_item_deserialization_create_only_required(self):
        sample = self.data_factory.create_item_sample(
            collection=self.collection.model, sample='item-1', required_only=True
        )

        # translate to Python native:
        serializer = ItemSerializer(data=sample.get_json('deserialize'))
        serializer.is_valid(raise_exception=True)
        item = serializer.save(collection=self.collection.model)

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        context = {
            'request':
                request_with_resolver(
                    f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{sample["name"]}'
                )
        }
        serializer = ItemSerializer(item, context=context)
        python_native = serializer.data
        self.check_stac_item(sample.json, python_native, self.collection["name"])

    def test_item_deserialization_create_only_required_2(self):
        sample = self.data_factory.create_item_sample(
            collection=self.collection.model, sample='item-2', required_only=True
        )

        # translate to Python native:
        serializer = ItemSerializer(data=sample.get_json('deserialize'))
        serializer.is_valid(raise_exception=True)
        item = serializer.save(collection=self.collection.model)

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        context = {
            'request':
                request_with_resolver(
                    f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{sample["name"]}'
                )
        }
        serializer = ItemSerializer(item, context=context)
        python_native = serializer.data
        self.check_stac_item(sample.json, python_native, self.collection["name"])

    def test_item_deserialization_create_full(self):
        sample = self.data_factory.create_item_sample(
            collection=self.collection.model, sample='item-1'
        )

        # translate to Python native:
        serializer = ItemSerializer(data=sample.get_json('deserialize'))
        serializer.is_valid(raise_exception=True)
        item = serializer.save(collection=self.collection.model)

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        context = {
            'request':
                request_with_resolver(
                    f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{sample["name"]}'
                )
        }
        serializer = ItemSerializer(item, context=context)
        python_native = serializer.data
        self.check_stac_item(sample.json, python_native, self.collection["name"])

    def test_item_deserialization_update(self):
        original_sample = self.data_factory.create_item_sample(
            collection=self.collection.model,
            sample='item-1',
        )
        sample = self.data_factory.create_item_sample(
            collection=self.collection.model, sample='item-2', name=original_sample["name"]
        )
        serializer = ItemSerializer(original_sample.model, data=sample.get_json('deserialize'))
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # mock a request needed for the serialization of links
        context = {
            'request':
                request_with_resolver(
                    f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{sample["name"]}'
                )
        }
        serializer = ItemSerializer(item, context=context)
        python_native = serializer.data
        self.check_stac_item(sample.json, python_native, self.collection["name"])
        self.assertIsNone(
            get_link(python_native['links'], 'describedBy'),
            msg='Link describedBy was not removed in update'
        )

    def test_item_deserialization_update_remove_title(self):
        original_sample = self.data_factory.create_item_sample(
            collection=self.collection.model,
            sample='item-1',
        )
        sample = self.data_factory.create_item_sample(
            collection=self.collection.model,
            sample='item-2',
            name=original_sample["name"],
            properties={"datetime": isoformat(utc_aware(datetime.utcnow()))}
        )
        serializer = ItemSerializer(original_sample.model, data=sample.get_json('deserialize'))
        serializer.is_valid(raise_exception=True)
        item = serializer.save()

        # mock a request needed for the serialization of links
        context = {
            'request':
                request_with_resolver(
                    f'/{STAC_BASE_V}/collections/{self.collection["name"]}/items/{sample["name"]}'
                )
        }
        serializer = ItemSerializer(item, context=context)
        python_native = serializer.data
        self.check_stac_item(sample.json, python_native, self.collection["name"])
        self.assertNotIn('title', python_native['properties'].keys(), msg="Title was not removed")

    def test_item_deserialization_missing_required(self):
        data = OrderedDict([
            ("collection", self.collection["name"]),
            ("id", "test"),
        ])

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_item_deserialization_invalid_data(self):
        data = self.data_factory.create_item_sample(
            collection=self.collection.model,
            sample='item-invalid',
        ).get_json('deserialize')

        # translate to Python native:
        serializer = ItemSerializer(data=data)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_item_deserialization_end_date_before_start_date(self):
        today = datetime.utcnow()
        yesterday = today - timedelta(days=1)
        sample = self.data_factory.create_item_sample(
            collection=self.collection.model,
            sample='item-1',
            properties={
                'start_datetime': isoformat(utc_aware(today)),
                "end_datetime": isoformat(utc_aware(yesterday))
            }
        )

        # translate to Python native:
        serializer = ItemSerializer(data=sample.get_json('deserialize'))
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_item_deserialization_invalid_link(self):
        sample = self.data_factory.create_item_sample(
            collection=self.collection.model,
            sample='item-invalid-link',
        )

        # translate to Python native:
        serializer = ItemSerializer(data=sample.get_json('deserialize'))
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class AssetSerializationTestCase(MockS3PerTestMixin, StacBaseTestCase):

    def setUp(self):
        super().setUp()
        self.data_factory = Factory()
        self.collection = self.data_factory.create_collection_sample(db_create=True)
        self.item = self.data_factory.create_item_sample(
            collection=self.collection.model, db_create=True
        )
        self.asset = self.data_factory.create_asset_sample(item=self.item.model, db_create=True)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_serialization(self):
        collection_name = self.collection["name"]
        item_name = self.item["name"]
        asset_name = self.asset["name"]

        # mock a request needed for the serialization of links
        request_mocker = request_with_resolver(
            f'/{STAC_BASE_V}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        )

        # translate to Python native:
        serializer = AssetSerializer(self.asset.model, context={'request': request_mocker})
        python_native = serializer.data

        logger.debug('serialized fields:\n%s', pformat(serializer.fields))
        logger.debug('python native:\n%s', pformat(python_native))

        # translate to JSON:
        json_string = JSONRenderer().render(python_native, renderer_context={'indent': 2})
        logger.debug('json string: %s', json_string.decode("utf-8"))

        self.check_stac_asset(
            self.asset.json, python_native, collection_name, item_name, ignore=["item"]
        )


class AssetDeserializationTestCase(MockS3PerClassMixin, StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.data_factory = Factory()
        cls.collection = cls.data_factory.create_collection_sample(db_create=True)
        cls.item = cls.data_factory.create_item_sample(
            collection=cls.collection.model, db_create=True
        )

    def setUp(self):  # pylint: disable=invalid-name
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_asset_deserialization_create(self):
        sample = self.data_factory.create_asset_sample(
            sample='asset-no-checksum', item=self.item.model, create_asset_file=True
        )

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = sample['name']
        request_mocker = request_with_resolver(
            f'/{STAC_BASE_V}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        )

        serializer = AssetSerializer(
            data=sample.get_json('deserialize'), context={'request': request_mocker}
        )
        serializer.collection = self.collection.model
        serializer.is_valid(raise_exception=True)
        asset = serializer.save(
            item=self.item.model,
            file=get_asset_path(self.item.model, serializer.validated_data['name'])
        )
        serializer = AssetSerializer(asset, context={'request': request_mocker})
        python_native = serializer.data

        # ignoring item below, as it is a "write_only" field in the asset's serializer.
        # it will not be present in the mocked request's data.
        self.check_stac_asset(sample.json, python_native, collection_name, item_name)

    def test_asset_deserialization_create_required_fields_only(self):
        sample = self.data_factory.create_asset_sample(
            item=self.item.model, required_only=True, create_asset_file=True, file=b'dummy-asset'
        )

        # mock a request needed for the serialization of links
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = sample['name']
        request_mocker = request_with_resolver(
            f'/{STAC_BASE_V}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        )

        serializer = AssetSerializer(
            data=sample.get_json('deserialize'), context={'request': request_mocker}
        )
        serializer.collection = self.collection.model
        serializer.is_valid(raise_exception=True)
        asset = serializer.save(
            item=self.item.model,
            file=get_asset_path(self.item.model, serializer.validated_data['name'])
        )

        # serialize the object and test it against the one above
        # mock a request needed for the serialization of links
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = sample['name']
        request_mocker = request_with_resolver(
            f'/{STAC_BASE_V}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        )

        serializer = AssetSerializer(asset, context={'request': request_mocker})
        python_native = serializer.data

        # ignoring item below, as it is a "write_only" field in the asset's serializer.
        # it will not be present in the mocked request's data.
        self.check_stac_asset(sample.json, python_native, collection_name, item_name)

    def test_asset_deserialization_create_invalid_data(self):
        sample = self.data_factory.create_asset_sample(item=self.item.model, sample='asset-invalid')

        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = sample['name']
        request_mocker = request_with_resolver(
            f'/{STAC_BASE_V}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        )

        serializer = AssetSerializer(
            data=sample.get_json('deserialize'), context={'request': request_mocker}
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_asset_deserialization_invalid_proj_epsg(self):
        sample = self.data_factory.create_asset_sample(item=self.item.model, proj_epsg=2056.1)
        # mock a request needed for the serialization of links
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = sample['name']
        request_mocker = request_with_resolver(
            f'/{STAC_BASE_V}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        )

        serializer = AssetSerializer(
            data=sample.get_json('deserialize'), context={'request': request_mocker}
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_asset_deserialization_missing_required_item(self):
        sample = self.data_factory.create_asset_sample(
            item=self.item.model, sample='asset-missing-required'
        )
        # mock a request needed for the serialization of links
        collection_name = self.collection['name']
        item_name = self.item['name']
        asset_name = sample['name']
        request_mocker = request_with_resolver(
            f'/{STAC_BASE_V}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        )

        serializer = AssetSerializer(
            data=sample.get_json('deserialize'), context={'request': request_mocker}
        )
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)
