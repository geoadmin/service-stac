import logging
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError
from django.test import TestCase

from stac_api.models.collection import Collection
from stac_api.models.item import Item

from tests.tests_10.data_factory import CollectionFactory

logger = logging.getLogger(__name__)


# pylint: disable=too-many-public-methods
class ItemsModelTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        CollectionFactory().create_sample().create()

    def setUp(self):
        self.collection = Collection.objects.get(name='collection-1')

    def test_item_create_model(self):
        item = Item(
            collection=self.collection, name='item-1', properties_datetime=datetime.now(UTC)
        )
        item.full_clean()
        item.save()
        self.assertEqual('item-1', item.name)

    def test_item_create_model_invalid_datetime(self):
        with self.assertRaises(ValidationError, msg="no datetime is invalid"):
            item = Item(collection=self.collection, name='item-1')
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError, msg="only start_datetime is invalid"):
            item = Item(
                collection=self.collection,
                name='item-2',
                properties_start_datetime=datetime.now(UTC)
            )
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError, msg="only end_datetime is invalid"):
            item = Item(
                collection=self.collection,
                name='item-3',
                properties_end_datetime=datetime.now(UTC)
            )
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError, msg="only expires is invalid"):
            item = Item(
                collection=self.collection, name='item-3', properties_expires=datetime.now(UTC)
            )
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError, msg="datetime is not allowed with start_datetime"):
            item = Item(
                collection=self.collection,
                name='item-4',
                properties_datetime=datetime.now(UTC),
                properties_start_datetime=datetime.now(UTC),
                properties_end_datetime=datetime.now(UTC)
            )
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError):
            item = Item(collection=self.collection, name='item-1', properties_datetime='asd')
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError):
            item = Item(collection=self.collection, name='item-4', properties_start_datetime='asd')
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError):
            item = Item(collection=self.collection, name='item-1', properties_end_datetime='asd')
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError):
            item = Item(collection=self.collection, name='item-1', properties_expires='asd')
            item.full_clean()
            item.save()

    def test_item_create_model_raises_exception_if_end_datetime_before_start_datetime(self):
        with self.assertRaises(ValidationError):
            today = datetime.now(UTC)
            yesterday = today - timedelta(days=1)
            item = Item(
                collection=self.collection,
                name='item-5',
                properties_start_datetime=today,
                properties_end_datetime=yesterday
            )
            item.full_clean()
            item.save()

    def test_item_create_model_raises_exception_if_expires_in_the_past(self):
        with self.assertRaises(ValidationError):
            yesterday = datetime.now(UTC) - timedelta(days=1)
            item = Item(collection=self.collection, name='item-5', properties_expires=yesterday)
            item.full_clean()
            item.save()

    def test_item_create_model_expires_can_be_before_datetime(self):
        today = datetime.now(UTC) + timedelta(milliseconds=100)
        tomorrow = today + timedelta(days=1)
        item = Item(
            collection=self.collection,
            name='item-expires-before-datetime',
            properties_datetime=tomorrow,
            properties_expires=today
        )
        item.full_clean()
        item.save()

    def test_item_create_model_expires_can_be_before_end_datetime(self):
        today = datetime.now(UTC)
        middle = today + timedelta(days=0.5)
        tomorrow = today + timedelta(days=1)
        item = Item(
            collection=self.collection,
            name='item-expires-before-end-datetime',
            properties_start_datetime=today,
            properties_end_datetime=tomorrow,
            properties_expires=middle
        )
        item.full_clean()
        item.save()

    def test_item_create_model_valid_geometry(self):
        # a correct geometry should not pose any problems
        item = Item(
            collection=self.collection,
            properties_datetime=datetime.now(UTC),
            name='item-1',
            geometry=GEOSGeometry(
                'SRID=4326;POLYGON '
                '((5.96 45.82, 5.96 47.81, 10.49 47.81, 10.49 45.82, 5.96 45.82))'
            )
        )
        item.full_clean()
        item.save()

    def test_item_create_model_invalid_geometry(self):
        # a geometry with self-intersection should not be allowed
        with self.assertRaises(ValidationError):
            item = Item(
                collection=self.collection,
                properties_datetime=datetime.now(UTC),
                name='item-1',
                geometry=GEOSGeometry(
                    'SRID=4326;POLYGON '
                    '((5.96 45.82, 5.96 47.81, 10.49 45.82, 10.49 47.81, 5.96 45.82))'
                )
            )
            item.full_clean()
            item.save()

    def test_item_create_model_invalid_projection(self):
        # a geometry with a projection other than wgs84 should not be allowed
        with self.assertRaises(ValidationError):
            item = Item(
                collection=self.collection,
                properties_datetime=datetime.now(UTC),
                name='item-1',
                geometry=GEOSGeometry(
                    'SRID=2056;POLYGON ((2500000 1100000, 2600000 1100000, 2600000 1200000, ' \
                        '2500000 1200000, 2500000 1100000))'
                )
            )
            item.full_clean()
            item.save()

    def test_item_create_model_invalid_latitude(self):
        # a geometry with self-intersection should not be allowed
        with self.assertRaises(ValidationError):
            item = Item(
                collection=self.collection,
                properties_datetime=datetime.now(UTC),
                name='item-1',
                geometry=GEOSGeometry(
                    'SRID=4326;POLYGON '
                    '((5.96 45.82, 5.96 97.81, 10.49 97.81, 10.49 45.82, 5.96 45.82))'
                )
            )
            item.full_clean()
            item.save()

    def test_item_create_model_empty_geometry(self):
        # empty geometry should not be allowed
        with self.assertRaises(ValidationError):
            item = Item(
                collection=self.collection,
                properties_datetime=datetime.now(UTC),
                name='item-empty',
                geometry=GEOSGeometry('POLYGON EMPTY')
            )
            item.full_clean()
            item.save()

    def test_item_create_model_none_geometry(self):
        # None geometry should not be allowed
        with self.assertRaises(ValidationError):
            item = Item(
                collection=self.collection,
                properties_datetime=datetime.now(UTC),
                name='item-empty',
                geometry=None
            )
            item.full_clean()
            item.save()

    def test_item_create_model_valid_point_geometry(self):
        # a correct geometry should not pose any problems
        item = Item(
            collection=self.collection,
            properties_datetime=datetime.now(UTC),
            name='item-1',
            geometry=GEOSGeometry('SRID=4326;POINT (5.96 45.82)')
        )
        item.full_clean()
        item.save()

    def test_item_create_model_point_geometry_invalid_latitude(self):
        # a geometry with self-intersection should not be allowed
        with self.assertRaises(ValidationError):
            item = Item(
                collection=self.collection,
                properties_datetime=datetime.now(UTC),
                name='item-1',
                geometry=GEOSGeometry('SRID=4326;POINT (5.96 95.82)')
            )
            item.full_clean()
            item.save()

    def test_item_create_model_valid_linestring_geometry(self):
        # a correct geometry should not pose any problems
        item = Item(
            collection=self.collection,
            properties_datetime=datetime.now(UTC),
            name='item-1',
            geometry=GEOSGeometry('SRID=4326;LINESTRING (5.96 45.82, 5.96 47.81)')
        )
        item.full_clean()
        item.save()

    def test_item_create_model_sets_forecast_reference_datetime_as_expected_for_rfc3399_format(
        self
    ):
        item = Item(
            collection=self.collection,
            properties_datetime=datetime.now(UTC),
            name='item-1',
            forecast_reference_datetime="2024-11-06T12:34:56Z",
        )
        item.full_clean()
        item.save()
        self.assertEqual(
            item.forecast_reference_datetime,
            datetime(
                year=2024, month=11, day=6, hour=12, minute=34, second=56, tzinfo=timezone.utc
            )
        )

    def test_item_create_model_raises_exception_if_forecast_reference_datetime_invalid(self):
        with self.assertRaises(ValidationError):
            item = Item(
                collection=self.collection,
                properties_datetime=datetime.now(UTC),
                name='item-1',
                forecast_reference_datetime="06-11-2024T12:34:56Z",
            )
            item.full_clean()

    def test_item_create_model_sets_forecast_horizon_as_expected(self):
        item = Item(
            collection=self.collection,
            properties_datetime=datetime.now(UTC),
            name='item-1',
            forecast_horizon=timedelta(days=1, hours=2),
        )
        item.full_clean()
        item.save()
        self.assertEqual(item.forecast_horizon, timedelta(days=1, hours=2))

    def test_item_create_model_sets_forecast_duration_as_expected(self):
        item = Item(
            collection=self.collection,
            properties_datetime=datetime.now(UTC),
            name='item-1',
            forecast_duration=timedelta(days=1, hours=2),
        )
        item.full_clean()
        item.save()
        self.assertEqual(item.forecast_duration, timedelta(days=1, hours=2))

    def test_item_create_model_sets_forecast_variable_as_expected(self):
        item = Item(
            collection=self.collection,
            properties_datetime=datetime.now(UTC),
            name='item-1',
            forecast_variable="air_temperature",
        )
        item.full_clean()
        item.save()
        self.assertEqual(item.forecast_variable, "air_temperature")

    def test_item_create_model_sets_forecast_perturbed_as_expected_if_mode_known(self):
        item = Item(
            collection=self.collection,
            properties_datetime=datetime.now(UTC),
            name='item-1',
            forecast_perturbed=True,
        )
        item.full_clean()
        item.save()
        self.assertEqual(item.forecast_perturbed, True)

    def test_item_create_model_sets_forecast_perturbed_to_none_if_undefined(self):
        item = Item(
            collection=self.collection, properties_datetime=datetime.now(UTC), name='item-1'
        )
        item.full_clean()
        item.save()
        self.assertEqual(item.forecast_perturbed, None)
