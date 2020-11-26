import logging
from datetime import datetime

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Polygon
from django.test import TestCase

from stac_api.models import Item
from stac_api.utils import utc_aware

import tests.database as db

logger = logging.getLogger(__name__)


class ItemsToCollectionTestCase(TestCase):
    '''
    Testing the propagation of item geometries to the bbox of the collection
    '''

    def setUp(self):
        self.collection = db.create_collection('collection-1')
        self.item = Item.objects.create(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
            name='base-bbox',
            geometry=GEOSGeometry('SRID=4326;POLYGON '
                                  '((0 0, 0 45, 45 45, 45 0, 0 0))')
        )
        self.item.full_clean()
        self.item.save()

    def test_if_collection_gets_right_extent(self):
        # the collection has to have the bbox of the item
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)

    def test_if_new_collection_has_extent(self):
        # a new collection has no bbox yet
        collection_no_bbox = db.create_collection('collection-no-bbox')
        self.assertIsNone(collection_no_bbox.extent_geometry)

    def test_changing_bbox_with_bigger_item(self):
        # changing the size of the bbox of the collection
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)

        bigger_item = Item.objects.create(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
            name='bigger-bbox',
            geometry=GEOSGeometry('SRID=4326;POLYGON '
                                  '((0 0, 0 50, 50 50, 50 0, 0 0))')
        )
        bigger_item.full_clean()
        bigger_item.save()
        # collection has to have the size of the bigger extent
        self.assertEqual(self.collection.extent_geometry, bigger_item.geometry)

        bigger_item.delete()
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)

    def test_changing_bbox_with_smaller_item(self):
        # changing the size of the bbox of the collection
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)
        smaller_item = Item.objects.create(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
            name='bigger-bbox',
            geometry=GEOSGeometry('SRID=4326;POLYGON '
                                  '((1 1, 1 40, 40 40, 40 1, 1 1))')
        )
        smaller_item.full_clean()
        smaller_item.save()
        # collection has to have the size of the bigger extent
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)
        smaller_item.delete()
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)

    def test_changing_bbox_with_diagonal_update(self):
        # changing collection bbox by moving one of two geometries
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)
        diagonal_item = Item.objects.create(
            collection=self.collection,
            properties_datetime=utc_aware(datetime.utcnow()),
            name='bigger-bbox',
            geometry=GEOSGeometry('SRID=4326;POLYGON '
                                  '((45 45, 45 90, 90 90, 90 45, 45 45))')
        )
        diagonal_item.full_clean()
        diagonal_item.save()
        # collection bbox composed of the two diagonal geometries
        self.assertEqual(
            GEOSGeometry(self.collection.extent_geometry).extent,
            GEOSGeometry(Polygon.from_bbox((0, 0, 90, 90))).extent
        )
        # moving the second geometrie to be on top of the other one
        diagonal_item.geometry = GEOSGeometry(
            'SRID=4326;POLYGON '
            '((0 0, 0 45, 45 45, 45 0, 0 0))'
        )
        diagonal_item.full_clean()
        diagonal_item.save()
        self.assertEqual(
            GEOSGeometry(self.collection.extent_geometry).extent,
            GEOSGeometry(Polygon.from_bbox((0, 0, 45, 45))).extent
        )

        diagonal_item.delete()
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)

    def test_collection_lost_all_items(self):
        self.item.delete()  # should be the one and only item of this collection
        self.assertIsNone(self.collection.extent_geometry)
