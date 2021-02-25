import logging
from datetime import datetime

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Polygon
from django.test import TestCase

from stac_api.models import Item
from stac_api.utils import utc_aware

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


class CollectionsModelTemporalExtentTestCase(TestCase):
    '''
    Testing the propagation of item temporal extent to the temporal extent of the collection
    '''

    y100 = utc_aware(datetime.strptime('0100-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
    y150 = utc_aware(datetime.strptime('0150-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
    y200 = utc_aware(datetime.strptime('0200-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
    y250 = utc_aware(datetime.strptime('0250-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
    y8000 = utc_aware(datetime.strptime('8000-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
    y8500 = utc_aware(datetime.strptime('8500-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
    y9000 = utc_aware(datetime.strptime('9000-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
    y9500 = utc_aware(datetime.strptime('9500-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))

    def setUp(self):
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model

    def add_range_item(self, start, end, name):
        item = self.factory.create_item_sample(
            self.collection,
            name=name,
            sample='item-2',
            properties_start_datetime=start,
            properties_end_datetime=end,
        )
        item.create()
        return item.model

    def add_single_datetime_item(self, datetime_val, name):
        item = self.factory.create_item_sample(
            self.collection, name=name, properties_datetime=datetime_val
        )
        return item.model

    def test_update_temporal_extent_range(self):
        # Tests if the collection's temporal extent is correctly updated, when
        # and item with a time range is added. When a second item with earlier
        # start_ and later end_datetime, tests, if collection's temporal extent
        # is updated correctly.

        # create an item with from year 200 to year 8000
        y200_y8000 = self.add_range_item(self.y200, self.y8000, 'y200_y8000')

        # now the collections start_ and end_datetime should be same as
        # the ones of item earliest_to_latest:
        self.assertEqual(
            self.collection.extent_start_datetime,
            y200_y8000.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "based on range of collection's items failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y200_y8000.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "based on range of collection's items failed."
        )

        # when adding a second item with earlier start and later end_datetime,
        # collections temporal range should be updated accordingly
        # create an item with from year 100 to year 9000
        y100_y9000 = self.add_range_item(self.y100, self.y9000, 'y100_y9000')

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100_y9000.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "based on range of collection's items failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y100_y9000.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "based on range of collection's items failed."
        )

    def test_update_temporal_extent_update_range_bounds_later_start_earlier_end(self):
        # Tests, if the collection's temporal extent is updated correctly, when
        # the bounds of the only item are updated separately, so that new start
        # date is later and new end date earlier.

        y100_y9000 = self.add_range_item(self.y100, self.y9000, 'y100_y9000')

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100_y9000.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "based on range of collection's item failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y100_y9000.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "based on range of collection's item failed."
        )

        y100_y9000.properties_start_datetime = self.y200
        y100_y9000.full_clean()
        y100_y9000.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100_y9000.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "after only item's start_datetime was updated failed."
        )

        y100_y9000.properties_end_datetime = self.y8000
        y100_y9000.full_clean()
        y100_y9000.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_end_datetime,
            y100_y9000.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "after only item's end_datetime was updated failed."
        )

    def test_update_temporal_extent_update_range_bounds_earlier_start_later_end(self):
        # Tests, if the collection's temporal extent is updated correctly, when
        # the bounds of the only item are updated separately, so that new start
        # date is earlier and new end date later.

        y200_y8000 = self.add_range_item(self.y200, self.y8000, 'y200_y8000')

        self.assertEqual(
            self.collection.extent_start_datetime,
            y200_y8000.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "based on range of collection's item failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y200_y8000.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "based on range of collection's item failed."
        )

        y200_y8000.properties_start_datetime = self.y100
        y200_y8000.full_clean()
        y200_y8000.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y200_y8000.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "after only item's start_datetime was updated failed."
        )

        y200_y8000.properties_end_datetime = self.y9000
        y200_y8000.full_clean()
        y200_y8000.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_end_datetime,
            y200_y8000.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "after only item's end_datetime was updated failed."
        )

    def test_update_temporal_extent_update_range_bounds_defining_item(self):
        # Tests, if the collection's temporal extent is updated correctly, when
        # the bounds of the item, that defines the collection's bounds are are
        # updated (first separately, then back again and then both at same time).

        y200_y8500 = self.add_range_item(self.y200, self.y8500, 'y200_8500')
        y100_y9500 = self.add_range_item(self.y100, self.y9500, 'y100_y9500')

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100_y9500.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "based on range of collection's oldest item failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y100_y9500.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "based on range of collection's latest item failed."
        )

        y100_y9500.properties_start_datetime = self.y150
        y100_y9500.full_clean()
        y100_y9500.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100_y9500.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "after item that defined the start_datetime was updated failed."
        )

        y100_y9500.properties_end_datetime = self.y9000
        y100_y9500.full_clean()
        y100_y9500.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_end_datetime,
            y100_y9500.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "after only item's end_datetime was updated failed."
        )

        y100_y9500.properties_start_datetime = self.y250
        y100_y9500.full_clean()
        y100_y9500.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y200_y8500.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "after item that defined the start_datetime was updated failed."
        )

        y100_y9500.properties_end_datetime = self.y8000
        y100_y9500.full_clean()
        y100_y9500.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_end_datetime,
            y200_y8500.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "after only item's end_datetime was updated failed."
        )

        y100_y9500.properties_start_datetime = self.y100
        y100_y9500.properties_end_datetime = self.y9500
        y100_y9500.full_clean()
        y100_y9500.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100_y9500.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "after item that defined the start_datetime was updated failed."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            y100_y9500.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "after only item's end_datetime was updated failed."
        )

        y100_y9500.properties_start_datetime = self.y250
        y100_y9500.properties_end_datetime = self.y8000
        y100_y9500.full_clean()
        y100_y9500.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y200_y8500.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "after item that defined the start_datetime was updated failed."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            y200_y8500.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "after only item's end_datetime was updated failed."
        )

    def test_update_temporal_extent_deletion_range_item(self):
        # Two items are added to the collection and one is deleted afterwards.
        # After the deletion, it is checked, that the temporal
        # extent of the collection is updated accordingly.

        # create an item with from year 200 to year 8000
        y200_y8000 = self.add_range_item(self.y200, self.y8000, 'y200_y8000')

        # create an item with from year 100 to year 9000
        y100_y9000 = self.add_range_item(self.y100, self.y9000, 'y100_y9000')

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100_y9000.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) of collection "
            "based on range of collection's items failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y100_y9000.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) of collection "
            "based on range of collection's items failed."
        )

        # now delete the one with the earlier start and later end_datetime first:
        Item.objects.get(pk=y100_y9000.pk).delete()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y200_y8000.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) after deletion of "
            "2nd last item failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y200_y8000.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) after deletion of "
            "2nd last item failed."
        )

    def test_update_temporal_extent_deletion_last_range_item(self):
        # An item is added to the collection and deleted again afterwards.
        # After the deletion, it is checked, that the temporal
        # extent of the collection is updated accordingly.

        # create an item with from year 200 to year 8000
        y200_y8000 = self.add_range_item(self.y200, self.y8000, 'y200_y8000')

        self.assertEqual(
            self.collection.extent_start_datetime,
            y200_y8000.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) after deletion of "
            "2nd last item failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y200_y8000.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) after deletion of "
            "2nd last item failed."
        )

        # now delete the only and hence last item of the collection:
        Item.objects.get(pk=y200_y8000.pk).delete()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            None,
            "Updating temporal extent (extent_start_datetime) after deletion of last "
            "item in collection failed."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            None,
            "Updating temporal extent (extent_end_datetime) after deletion of last "
            "item in collection failed."
        )

    def test_update_temporal_extent_switch_range_datetime(self):
        # Two items with start_ and end_datetimes are added. Afterwards they are
        # updated to no longer have start_ and end_datetimes each has a single
        # datetime value. Update of the collection's temporal extent is checked.
        # Finally one item is deleted, so that the collection's temporal extent
        # should be [last_items_datetime, last_items_datetime]

        # create an item with from year 200 to year 8000
        y200_y8000 = self.add_range_item(self.y200, self.y8000, 'y200_y8000')

        # create an item with from year 100 to year 9000
        y100_y9000 = self.add_range_item(self.y100, self.y9000, 'y100_y9000')

        y200_y8000.properties_start_datetime = None
        y200_y8000.properties_end_datetime = None
        y200_y8000.properties_datetime = self.y200
        y200_y8000.full_clean()
        y200_y8000.save()
        self.collection.refresh_from_db()

        y100_y9000.properties_start_datetime = None
        y100_y9000.properties_end_datetime = None
        y100_y9000.properties_datetime = self.y9000
        y100_y9000.full_clean()
        y100_y9000.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y200_y8000.properties_datetime,
            "Updating temporal extent (extent_start_datetime) after updating "
            "item from start_ and end_datetime to single datetime value "
            "failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y100_y9000.properties_datetime,
            "Updating temporal extent (extent_end_datetime) after updating "
            "item from start_ and end_datetime to single datetime value "
            "failed."
        )

        Item.objects.get(pk=y200_y8000.pk).delete()
        self.collection.refresh_from_db()

        # refresh collection from db
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100_y9000.properties_datetime,
            "Updating temporal extent (extent_start_datetime) based on a "
            "single item's datetime property failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y100_y9000.properties_datetime,
            "Updating temporal extent (extent_end_datetime) based on a "
            "single item's datetime property failed."
        )

    def test_update_temporal_extent_datetime(self):
        # Tests if the collection's temporal extent is correctly updated, when
        # and item with a single datetime value is added. When a second item
        # with earlier start_datetime is added, it is checked, if collection's
        # temporal extent is updated correctly. Analogue for adding a third item
        # with later end_datetime

        y200 = self.add_single_datetime_item(self.y200, 'y200')

        self.assertEqual(
            self.collection.extent_start_datetime,
            y200.properties_datetime,
            "Updating temporal extent (extent_start_datetime) based on a "
            "single item's datetime property failed."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            y200.properties_datetime,
            "Updating temporal extent (extent_end_datetime) based on a "
            "single item's datetime property failed."
        )

        y100 = self.add_single_datetime_item(self.y100, 'y100')

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100.properties_datetime,
            "Updating temporal extent (extent_start_datetime) after adding "
            "a second item with singe datetime property failed."
        )

        y8000 = self.add_single_datetime_item(self.y8000, 'y8000')

        self.assertEqual(
            self.collection.extent_end_datetime,
            y8000.properties_datetime,
            "Updating temporal extent (extent_end_datetime) after adding "
            "a third item with singe datetime property failed."
        )

    def test_update_temporal_extent_update_datetime_property(self):
        # Test if the collection's temporal extent is updated correctly, when the
        # datetime value of the only existing item is updated.

        y8000 = self.add_single_datetime_item(self.y8000, 'y8000')
        self.assertEqual(
            self.collection.extent_start_datetime,
            y8000.properties_datetime,
            "Updating temporal extent (extent_start_datetime) based on the "
            "only item's datetime."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            y8000.properties_datetime,
            "Updating temporal extent (extent_start_datetime) based on the "
            "only item's datetime."
        )

        y8000.properties_datetime = self.y100
        y8000.full_clean()
        y8000.save()

        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y8000.properties_datetime,
            "Updating temporal extent (extent_start_datetime) after datetime "
            "of the only item was updated."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            y8000.properties_datetime,
            "Updating temporal extent (extent_start_datetime) after datetime "
            "of the only item was updated."
        )

    def test_update_temporal_extent_update_datetime_property_defining_item(self):
        # Test if the collection's temporal extent is updated correctly, when the
        # datetime value of the item is updated, that defines a bound of the
        # collection's temporal extent.

        y100 = self.add_single_datetime_item(self.y200, 'y100')
        y200 = self.add_single_datetime_item(self.y200, 'y200')
        y8500 = self.add_single_datetime_item(self.y8500, 'y8500')
        y9500 = self.add_single_datetime_item(self.y9500, 'y9500')

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100.properties_datetime,
            "Updating temporal extent (extent_start_datetime) based on the "
            "oldest item's datetime."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            y9500.properties_datetime,
            "Updating temporal extent (extent_end_datetime) based on the "
            "latest item's datetime."
        )

        y9500.properties_datetime = self.y9000
        y9500.full_clean()
        y9500.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_end_datetime,
            y9500.properties_datetime,
            "Updating temporal extent (extent_start_datetime) after datetime "
            "of the latest item was updated."
        )

        y100.properties_datetime = self.y150
        y100.full_clean()
        y100.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100.properties_datetime,
            "Updating temporal extent (extent_start_datetime) after datetime "
            "of the oldest item was updated."
        )

        y9500.properties_datetime = self.y8000
        y9500.full_clean()
        y9500.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_end_datetime,
            y8500.properties_datetime,
            "Updating temporal extent (extent_end_datetime) after datetime "
            "of the latest item was updated."
        )

        y100.properties_datetime = self.y250
        y100.full_clean()
        y100.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y200.properties_datetime,
            "Updating temporal extent (extent_start_datetime) after datetime "
            "of the oldest item was updated."
        )

    def test_update_temporal_extent_deletion_older_datetime_item(self):
        # Two items with single datetime values are added and the older one is
        # deleted afterwards. It is checked, if the collection's temporal
        # extent is updated correctly.

        y200 = self.add_single_datetime_item(self.y200, 'y200')

        y100 = self.add_single_datetime_item(self.y100, 'y100')

        # now delete one item:
        Item.objects.get(pk=y100.pk).delete()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y200.properties_datetime,
            "Updating temporal extent (extent_start_datetime) after deletion of "
            "2nd last item failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y200.properties_datetime,
            "Updating temporal extent (extent_end_datetime) after deletion of "
            "2nd last item failed."
        )

    def test_update_temporal_extent_deletion_younger_datetime_item(self):
        # Two items with single datetime values are added and the younger one is
        # deleted afterwards. It is checked, if the collection's temporal
        # extent is updated correctly.

        y200 = self.add_single_datetime_item(self.y200, 'y200')
        y100 = self.add_single_datetime_item(self.y100, 'y100')

        # now delete one item:
        Item.objects.get(pk=y200.pk).delete()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100.properties_datetime,
            "Updating temporal extent (extent_start_datetime) after deletion of "
            "2nd last item failed."
        )
        self.assertEqual(
            self.collection.extent_end_datetime,
            y100.properties_datetime,
            "Updating temporal extent (extent_end_datetime) after deletion of "
            "2nd last item failed."
        )

    def test_update_temporal_extent_deletion_last_datetime_item(self):
        # An item is added to the collection and deleted again afterwards.
        # After the deletion, it is checked, that the temporal
        # extent of the collection is updated accordingly.

        y200 = self.add_single_datetime_item(self.y200, 'y200')
        Item.objects.get(pk=y200.pk).delete()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            None,
            "Updating temporal extent (extent_start_datetime) after deletion of last "
            "item in collection failed."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            None,
            "Updating temporal extent (extent_end_datetime) after deletion of last "
            "item in collection failed."
        )

    def test_update_temporal_extent_switch_datetime_range(self):
        # An item with a single datetime value is added. Afterwards it is updated
        # to have start_ and end_datetimes instead. Update of the collection's
        # temporal extent is checked.

        y200 = self.add_single_datetime_item(self.y200, 'y200')
        y200.properties_datetime = None
        y200.properties_start_datetime = self.y100
        y200.properties_end_datetime = self.y8000
        y200.full_clean()
        y200.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            self.y100,
            "Updating temporal extent (extent_start_datetime) after updating "
            "item from single datetime to a range failed."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            self.y8000,
            "Updating temporal extent (extent_end_datetime) after updating "
            "item from single datetime to a range failed."
        )

    def test_update_temporal_extent_datetime_mixed_items(self):
        # Tests, if collection's temporal extent is updated correctly when
        # mixing items with ranges and single datetime values.

        y100 = self.add_single_datetime_item(self.y100, 'y100')
        y9000 = self.add_single_datetime_item(self.y9000, 'y9000')
        y200_y8000 = self.add_range_item(self.y200, self.y8000, 'y200_y8000')

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100.properties_datetime,
            "Updating temporal extent (extent_start_datetime) based on mixed "
            "items failed."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            y9000.properties_datetime,
            "Updating temporal extent (extent_end_datetime) based on mixed "
            "items failed."
        )

        y100.properties_datetime = self.y200
        y100.full_clean()
        y100.save()
        y9000.properties_datetime = self.y8000
        y9000.full_clean()
        y9000.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100.properties_datetime,
            "Updating temporal extent (extent_start_datetime) based on mixed "
            "items failed."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            y9000.properties_datetime,
            "Updating temporal extent (extent_end_datetime) based on mixed "
            "items failed."
        )

        y100_y9000 = self.add_range_item(self.y100, self.y9000, 'y100_y9000')

        self.assertEqual(
            self.collection.extent_start_datetime,
            y100_y9000.properties_start_datetime,
            "Updating temporal extent (extent_start_datetime) based on mixed "
            "items failed."
        )

        self.assertEqual(
            self.collection.extent_end_datetime,
            y100_y9000.properties_end_datetime,
            "Updating temporal extent (extent_end_datetime) based on mixed "
            "items failed."
        )
