import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError
from django.test import TestCase

from stac_api.models import Collection
from stac_api.models import Item
from stac_api.utils import utc_aware

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
            collection=self.collection,
            name='item-1',
            properties_datetime=utc_aware(datetime.utcnow())
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
                properties_start_datetime=utc_aware(datetime.utcnow())
            )
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError, msg="only end_datetime is invalid"):
            item = Item(
                collection=self.collection,
                name='item-3',
                properties_end_datetime=utc_aware(datetime.utcnow())
            )
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError, msg="only expires is invalid"):
            item = Item(
                collection=self.collection,
                name='item-3',
                properties_expires=utc_aware(datetime.utcnow())
            )
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError, msg="datetime is not allowed with start_datetime"):
            item = Item(
                collection=self.collection,
                name='item-4',
                properties_datetime=utc_aware(datetime.utcnow()),
                properties_start_datetime=utc_aware(datetime.utcnow()),
                properties_end_datetime=utc_aware(datetime.utcnow())
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

    def test_item_create_model_invalid_datetime_order(self):
        with self.assertRaises(
            ValidationError, msg="end_datetime must not be earlier than start_datetime"
        ):
            today = datetime.utcnow()
            yesterday = today - timedelta(days=1)
            item = Item(
                collection=self.collection,
                name='item-5',
                properties_start_datetime=utc_aware(today),
                properties_end_datetime=utc_aware(yesterday)
            )
            item.full_clean()
            item.save()

        with self.assertRaises(
            ValidationError, msg="expires must not be earlier than end_datetime"
        ):
            today = datetime.utcnow()
            yesterday = today - timedelta(days=1)
            item = Item(
                collection=self.collection,
                name='item-5',
                properties_end_datetime=utc_aware(today),
                properties_expires=utc_aware(yesterday)
            )
            item.full_clean()
            item.save()

        with self.assertRaises(ValidationError, msg="expires must not be earlier than datetime"):
            today = datetime.utcnow()
            yesterday = today - timedelta(days=1)
            item = Item(
                collection=self.collection,
                name='item-5',
                properties_datetime=utc_aware(today),
                properties_expires=utc_aware(yesterday)
            )
            item.full_clean()
            item.save()

    def test_item_create_model_valid_geometry(self):
        # a correct geometry should not pose any problems
        item = Item(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
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
                properties_datetime=utc_aware(datetime.utcnow()),
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
                properties_datetime=utc_aware(datetime.utcnow()),
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
                properties_datetime=utc_aware(datetime.utcnow()),
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
                properties_datetime=utc_aware(datetime.utcnow()),
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
                properties_datetime=utc_aware(datetime.utcnow()),
                name='item-empty',
                geometry=None
            )
            item.full_clean()
            item.save()

    def test_item_create_model_valid_point_geometry(self):
        # a correct geometry should not pose any problems
        item = Item(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
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
                properties_datetime=utc_aware(datetime.utcnow()),
                name='item-1',
                geometry=GEOSGeometry('SRID=4326;POINT (5.96 95.82)')
            )
            item.full_clean()
            item.save()

    def test_item_create_model_valid_linestring_geometry(self):
        # a correct geometry should not pose any problems
        item = Item(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
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
            properties_datetime=utc_aware(datetime.utcnow()),
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
                properties_datetime=utc_aware(datetime.utcnow()),
                name='item-1',
                forecast_reference_datetime="06-11-2024T12:34:56Z",
            )
            item.full_clean()

    def test_item_create_model_sets_forecast_horizon_as_expected(self):
        item = Item(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
            name='item-1',
            forecast_horizon=timedelta(days=1, hours=2),
        )
        item.full_clean()
        item.save()
        self.assertEqual(item.forecast_horizon, timedelta(days=1, hours=2))

    def test_item_create_model_sets_forecast_duration_as_expected(self):
        item = Item(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
            name='item-1',
            forecast_duration=timedelta(days=1, hours=2),
        )
        item.full_clean()
        item.save()
        self.assertEqual(item.forecast_duration, timedelta(days=1, hours=2))

    def test_item_create_model_sets_forecast_param_as_expected(self):
        item = Item(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
            name='item-1',
            forecast_param="T",
        )
        item.full_clean()
        item.save()
        self.assertEqual(item.forecast_param, "T")

    def test_item_create_model_sets_forecast_mode_as_expected_if_mode_known(self):
        item = Item(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
            name='item-1',
            forecast_mode="ctrl",
        )
        item.full_clean()
        item.save()
        self.assertEqual(item.forecast_mode, "ctrl")

    def test_item_create_model_raises_exception_if_value_of_forecast_mode_unknown(self):
        with self.assertRaises(ValidationError):
            item = Item(
                collection=self.collection,
                properties_datetime=utc_aware(datetime.utcnow()),
                name='item-1',
                forecast_mode="unknown mode",
            )
            item.full_clean()

    def test_item_create_model_sets_forecast_mode_to_none_if_undefined(self):
        item = Item(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
            name='item-1'
        )
        item.full_clean()
        item.save()
        self.assertEqual(item.forecast_mode, None)
