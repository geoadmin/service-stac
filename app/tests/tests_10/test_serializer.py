# pylint: disable=too-many-lines

import logging
import unittest
import zoneinfo
from collections import OrderedDict
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pprint import pformat

from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import IntegrityError
from django.urls import resolve

from rest_framework import serializers
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIRequestFactory

from stac_api.serializers.collection import CollectionSerializer
from stac_api.serializers.item import AssetSerializer
from stac_api.serializers.item import ItemListSerializer
from stac_api.serializers.item import ItemSerializer
from stac_api.serializers.item import ItemsPropertiesSerializer
from stac_api.utils import get_asset_path
from stac_api.utils import get_link
from stac_api.utils import isoformat

from tests.tests_10.base_test import STAC_BASE_V
from tests.tests_10.base_test import STAC_VERSION
from tests.tests_10.base_test import StacBaseTestCase
from tests.tests_10.base_test import StacBaseTransactionTestCase
from tests.tests_10.data_factory import Factory
from tests.tests_10.utils import calculate_extent
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
        self.collection_created_after = datetime.now(UTC)
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
                    ('href', f'http://testserver/api/stac/v1/collections/{collection_name}'),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', 'http://testserver/api/stac/v1/'),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    ('href', 'http://testserver/api/stac/v1/'),
                ]),
                OrderedDict([
                    ('rel', 'items'),
                    ('href', f'http://testserver/api/stac/v1/collections/{collection_name}/items'),
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
                'gsd': [3.4],
                'geoadmin:variant': ['kgrs'],
                'proj:epsg': [2056],
            },
            'updated': isoformat(self.collection_created_after)
        })
        self.check_stac_collection(expected, python_native)


class EmptyCollectionSerializationTestCase(StacBaseTransactionTestCase):

    def setUp(self):
        self.data_factory = Factory()
        self.collection_created_after = datetime.now(UTC)
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
                    ('href', f'http://testserver/api/stac/v1/collections/{collection_name}'),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', 'http://testserver/api/stac/v1/'),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    ('href', 'http://testserver/api/stac/v1/'),
                ]),
                OrderedDict([
                    ('rel', 'items'),
                    ('href', f'http://testserver/api/stac/v1/collections/{collection_name}/items'),
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
            properties={"datetime": isoformat(datetime.now(UTC))}
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
        today = datetime.now(UTC)
        yesterday = today - timedelta(days=1)
        sample = self.data_factory.create_item_sample(
            collection=self.collection.model,
            sample='item-1',
            properties={
                'start_datetime': isoformat(today), "end_datetime": isoformat(yesterday)
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


class ItemsPropertiesSerializerTestCase(unittest.TestCase):

    def test_deserialization_works_as_expected_for_valid_forecast_data(self):
        data = {
            "forecast:reference_datetime": "2024-11-19T16:15:00Z",
            "forecast:horizon": "P3DT2H",
            "forecast:duration": "PT4H",
            "forecast:variable": "air_temperature",
            "forecast:perturbed": False,
        }

        serializer = ItemsPropertiesSerializer(data=data)
        self.assertTrue(serializer.is_valid())

        self.assertEqual(
            serializer.validated_data["forecast_reference_datetime"],
            datetime(year=2024, month=11, day=19, hour=16, minute=15, tzinfo=timezone.utc)
        )
        self.assertEqual(serializer.validated_data["forecast_horizon"], timedelta(days=3, hours=2))
        self.assertEqual(serializer.validated_data["forecast_duration"], timedelta(hours=4))
        self.assertEqual(serializer.validated_data["forecast_variable"], data["forecast:variable"])
        self.assertEqual(
            serializer.validated_data["forecast_perturbed"], data["forecast:perturbed"]
        )

    def test_deserialization_detects_invalid_forecast_reference_datetime(self):
        data = {
            "forecast:reference_datetime": "🕒️",
        }

        serializer = ItemsPropertiesSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_deserialization_detects_invalid_forecast_horizon(self):
        wrong_order = "P1HT2D"
        data = {
            "forecast:horizon": wrong_order,
        }

        serializer = ItemsPropertiesSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_deserialization_detects_invalid_forecast_duration(self):
        missing_time_designator = "P2D1H"
        data = {
            "forecast:duration": missing_time_designator,
        }

        serializer = ItemsPropertiesSerializer(data=data)

        self.assertFalse(serializer.is_valid())

    def test_deserialization_detects_invalid_forecast_perturbed(self):
        nonexistant_perturbed = "bla"
        data = {
            "forecast:perturbed": nonexistant_perturbed,
        }

        serializer = ItemsPropertiesSerializer(data=data)

        self.assertFalse(serializer.is_valid())

    def test_serialization_works_as_expected_for_valid_forecast_data(self):
        data = {
            "forecast:reference_datetime": "2024-11-19T16:15:00Z",
            "forecast:horizon": "P3DT2H",
            "forecast:duration": "PT4H",
            "forecast:variable": "air_temperature",
            "forecast:perturbed": False,
        }

        serializer = ItemsPropertiesSerializer(data=data)
        self.assertTrue(serializer.is_valid())

        actual = serializer.to_representation(serializer.validated_data)

        self.assertEqual(actual["forecast:reference_datetime"], data["forecast:reference_datetime"])
        self.assertEqual(actual["forecast:horizon"], "P3DT02H00M00S")
        self.assertEqual(actual["forecast:duration"], "P0DT04H00M00S")
        self.assertEqual(actual["forecast:variable"], data["forecast:variable"])
        self.assertEqual(actual["forecast:perturbed"], data["forecast:perturbed"])


class ItemListDeserializationTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):  # pylint: disable=invalid-name
        cls.data_factory = Factory()
        cls.collection = cls.data_factory.create_collection_sample(db_create=True)
        cls.collection.model.allow_external_assets = True
        cls.collection.model.external_asset_whitelist = [settings.EXTERNAL_TEST_ASSET_URL]
        cls.collection.model.save()
        cls.payload = {
            "features": [
                {
                    "id": "item-1",
                    "assets": {
                        "asset-1.txt": {
                            "title": "My title 1",
                            "description": "My description 1",
                            "type": "text/plain",
                            "href": settings.EXTERNAL_TEST_ASSET_URL,
                            "roles": ["myrole"],
                            "geoadmin:variant": "komb",
                            "geoadmin:lang": "de",
                            "proj:epsg": 2056,
                            "gsd": 2.5
                        }
                    },
                    "geometry": {
                        "type": "Point", "coordinates": [1.1, 1.2]
                    },
                    "properties": {
                        "datetime": "2018-02-12T23:20:50Z",
                    },
                },
                {
                    "id": "item-2",
                    "assets": {
                        "asset-2.txt": {
                            "title": "My title 2",
                            "description": "My description 2",
                            "type": "text/plain",
                            "href": settings.EXTERNAL_TEST_ASSET_URL,
                            "roles": ["myrole"],
                            "geoadmin:variant": "komb",
                            "geoadmin:lang": "de",
                            "proj:epsg": 2056,
                            "gsd": 2.5
                        }
                    },
                    "geometry": {
                        "type": "Point", "coordinates": [2.1, 2.2]
                    },
                    "properties": {
                        "datetime": "2019-01-13T13:30:00Z",
                    },
                },
            ]
        }

    def setUp(self):  # pylint: disable=invalid-name
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_itemlistserializer_deserializes_list_of_items_as_expected(self):
        serializer = ItemListSerializer(
            data=self.payload, context={"collection": self.collection.model}
        )

        self.assertTrue(serializer.is_valid())

        actual = serializer.validated_data

        # ignore None values which are added by default
        actual["features"] = [{
            k: v for k, v in item.items() if v is not None
        } for item in actual["features"]]

        # Note: we have to keep the list here for the assets
        # since the serializer for the nested assets in his heart
        # is a list serializer and we fool him a little with converting
        # asset dicts to lists just before he gets to do something (see
        # DictSerializer in serializers/utils.py) and we're just testing
        # the serializer here and not the full chain.
        expected = {
            "features": [
                {
                    "name": "item-1",
                    "assets": [{
                        "name": "asset-1.txt",
                        "title": "My title 1",
                        "media_type": "text/plain",
                        "file": settings.EXTERNAL_TEST_ASSET_URL,
                        "description": "My description 1",
                        "roles": ["myrole"],
                        "eo_gsd": 2.5,
                        "proj_epsg": 2056,
                        "geoadmin_variant": "komb",
                        "geoadmin_lang": "de",
                    },],
                    "geometry": Point(1.1, 1.2, srid=4326),
                    "properties_datetime":
                        datetime(2018, 2, 12, 23, 20, 50, tzinfo=zoneinfo.ZoneInfo(key='UTC')),
                },
                {
                    "name": "item-2",
                    "assets": [{
                        "name": "asset-2.txt",
                        "title": "My title 2",
                        "media_type": "text/plain",
                        "file": settings.EXTERNAL_TEST_ASSET_URL,
                        "description": "My description 2",
                        "roles": ["myrole"],
                        "eo_gsd": 2.5,
                        "proj_epsg": 2056,
                        "geoadmin_variant": "komb",
                        "geoadmin_lang": "de",
                    },],
                    "geometry": Point(2.1, 2.2, srid=4326),
                    "properties_datetime":
                        datetime(2019, 1, 13, 13, 30, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')),
                },
            ]
        }
        self.assertDictEqual(expected, actual)

    def test_itemlistserializer_serializes_list_of_items_as_expected(self):
        request_mocker = request_with_resolver(
            f'/{STAC_BASE_V}/collections/{self.collection.model.name}/items'
        )
        serializer = ItemListSerializer(
            data=self.payload,
            context={
                'request': request_mocker, 'collection': self.collection.model
            }
        )

        self.assertTrue(serializer.is_valid())

        serializer.save(collection=self.collection.model)

        actual = serializer.data

        expected = self.payload.copy()
        expected["features"][0]["assets"] = {
            "asset-1.txt": {
                "gsd": 2.5,
                "geoadmin:variant": "komb",
                "href": settings.EXTERNAL_TEST_ASSET_URL,
                "proj:epsg": 2056,
                "type": "text/plain",
            },
        }
        expected["features"][1]["assets"] = {
            "asset-2.txt": {
                "gsd": 2.5,
                "geoadmin:variant": "komb",
                "href": settings.EXTERNAL_TEST_ASSET_URL,
                "proj:epsg": 2056,
                "type": "text/plain",
            },
        }
        for item_actual, item_expected in zip(actual["features"], expected["features"]):
            self.check_stac_item(item_expected, item_actual, self.collection.model.name)

    def test_itemlistserializer_throws_exception_if_item_exists_already(self):
        request_mocker = request_with_resolver(
            f'/{STAC_BASE_V}/collections/{self.collection.model.name}/items'
        )

        # Create two items
        serializer = ItemListSerializer(
            data=self.payload,
            context={
                'request': request_mocker, 'collection': self.collection.model
            }
        )
        self.assertTrue(serializer.is_valid())
        serializer.save(collection=self.collection.model)

        # Try to create the first item again but with a different time
        new_datetime = "2019-02-12T23:20:50+00:00"
        update_payload = {
            "features": [{
                "id": "item-1",
                "geometry": {
                    "type": "Point", "coordinates": [1.1, 1.2]
                },
                "properties": {
                    "datetime": new_datetime,
                },
            },]
        }
        serializer = ItemListSerializer(data=update_payload, context={'request': request_mocker})
        self.assertTrue(serializer.is_valid())

        with self.assertRaises(IntegrityError) as context:
            serializer.save(collection=self.collection.model)


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


class AssetDeserializationTestCase(MockS3PerTestMixin, StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.data_factory = Factory()
        cls.collection = cls.data_factory.create_collection_sample(db_create=True)
        cls.item = cls.data_factory.create_item_sample(
            collection=cls.collection.model, db_create=True
        )

    def setUp(self):  # pylint: disable=invalid-name
        super().setUp()
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
