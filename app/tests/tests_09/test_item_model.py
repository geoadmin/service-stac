import logging
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError
from django.test import TestCase

from stac_api.models.collection import Collection
from stac_api.models.item import Item

from tests.tests_09.data_factory import CollectionFactory

logger = logging.getLogger(__name__)


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

        with self.assertRaises(
            ValidationError, msg="end_datetime must not be earlier than start_datetime"
        ):
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
