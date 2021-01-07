import logging

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Polygon
from django.test import TestCase

from tests.data_factory import Factory

logger = logging.getLogger(__name__)


class CollectionSpatialExtentTestCase(TestCase):
    '''
    Testing the propagation of item geometries to the bbox of the collection
    '''

    def setUp(self):
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(
            collection=self.collection,
            name='base-bbox',
            geometry=GEOSGeometry('SRID=4326;POLYGON ((0 0, 0 45, 45 45, 45 0, 0 0))')
        ).model

    def test_if_collection_gets_right_extent(self):
        # the collection has to have the bbox of the item
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)

    def test_if_new_collection_has_extent(self):
        # a new collection has no bbox yet
        collection_no_bbox = self.factory.create_collection_sample(name='collection-no-bbox').model
        self.assertIsNone(collection_no_bbox.extent_geometry)

    def test_changing_bbox_with_bigger_item(self):
        # changing the size of the bbox of the collection
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)

        bigger_item = self.factory.create_item_sample(
            self.collection,
            name='bigger-bbox',
            geometry=GEOSGeometry('SRID=4326;POLYGON ((0 0, 0 50, 50 50, 50 0, 0 0))')
        ).model
        # collection has to have the size of the bigger extent
        self.assertEqual(self.collection.extent_geometry, bigger_item.geometry)

        bigger_item.delete()
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)

    def test_changing_bbox_with_smaller_item(self):
        # changing the size of the bbox of the collection
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)
        smaller_item = self.factory.create_item_sample(
            self.collection,
            name='smaller-bbox',
            geometry=GEOSGeometry('SRID=4326;POLYGON ((1 1, 1 40, 40 40, 40 1, 1 1))')
        ).model

        # collection has to have the size of the bigger extent
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)
        smaller_item.delete()
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)

    def test_changing_bbox_with_diagonal_update(self):
        # changing collection bbox by moving one of two geometries
        self.assertEqual(self.collection.extent_geometry, self.item.geometry)
        diagonal_item = self.factory.create_item_sample(
            self.collection,
            name='diagonal-bbox',
            geometry=GEOSGeometry('SRID=4326;POLYGON ((45 45, 45 90, 90 90, 90 45, 45 45))')
        ).model
        # collection bbox composed of the two diagonal geometries
        self.assertEqual(
            GEOSGeometry(self.collection.extent_geometry).extent,
            GEOSGeometry(Polygon.from_bbox((0, 0, 90, 90))).extent
        )
        # moving the second geometry to be on top of the other one
        diagonal_item.geometry = GEOSGeometry('SRID=4326;POLYGON ((0 0, 0 45, 45 45, 45 0, 0 0))')
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
