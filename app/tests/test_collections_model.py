import logging
from datetime import datetime

from django.conf import settings
from django.test import TestCase

from stac_api.models import Item
from stac_api.utils import utc_aware

import tests.database as db

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


class CollectionsModelTestCase(TestCase):

    def setUp(self):
        self.collection = db.create_collection('collection-1')

    def test_update_temporal_extent_range(self):
        '''
        test, if the collection's temporal extent is correctly updated, when
        and item is added. This test starts with items that have a range
        defined initially (start_ and end_datetime).
        For testing, an item will be updated as to have a properties.datetime only
        and no longer a range.
        '''

        start_earliest = utc_aware(datetime.strptime('0001-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
        end_latest = utc_aware(datetime.strptime('9999-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
        start_2nd_earliest = utc_aware(
            datetime.strptime('0010-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ')
        )
        end_2nd_latest = utc_aware(datetime.strptime('9990-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))

        # create an item with a really early start_datetime and an
        # end_datetime in the far future
        item_earliest_to_latest = Item.objects.create(
            collection=self.collection,
            item_name='earliest_to_latest',
            properties_start_datetime=start_earliest,
            properties_end_datetime=end_latest,
            properties_eo_gsd=None,
            properties_title="My Title",
        )
        db.create_item_links(item_earliest_to_latest)
        item_earliest_to_latest.save()
        self.collection.save()

        # create the 2nd oldest item with the second furthest away end_datetime in future
        item_2nd_earliest_to_2nd_latest = Item.objects.create(
            collection=self.collection,
            item_name='2nd_earliest_to_2nd_latest',
            properties_start_datetime=start_2nd_earliest,
            properties_end_datetime=end_2nd_latest,
            properties_eo_gsd=None,
            properties_title="My Title",
        )
        db.create_item_links(item_2nd_earliest_to_2nd_latest)
        item_2nd_earliest_to_2nd_latest.save()
        self.collection.save()

        # now the collections start_ and end_datetime should be same as
        # the ones of item_earliest_to_latest:
        self.assertEqual(
            self.collection.cache_start_datetime,
            item_earliest_to_latest.properties_start_datetime,
            "Updating temporal extent (cache_start_datetime) of collection "
            "based on range of collection's items failed."
        )
        self.assertEqual(
            self.collection.cache_end_datetime,
            item_earliest_to_latest.properties_end_datetime,
            "Updating temporal extent (cache_end_datetime) of collection "
            "based on range of collection's items failed."
        )

        # after deleting item_earliest_to_latest, collection's start_ and
        # end_datetime should be equal to those of
        # item_2nd_earliest_to_2nd_latest.
        Item.objects.get(pk=item_earliest_to_latest.pk).delete()

        # logger.debug(
        #     "before save %s %s ",
        #     self.collection.cache_start_datetime,
        #     self.collection.cache_end_datetime
        # )

        # refresh collection from db
        self.collection.refresh_from_db()

        # logger.debug(
        #    "after save and refresh %s %s ",
        #    self.collection.cache_start_datetime,
        #    self.collection.cache_end_datetime
        # )
        self.assertEqual(
            self.collection.cache_start_datetime,
            item_2nd_earliest_to_2nd_latest.properties_start_datetime,
            "Updating temporal extent (cache_start_datetime) of collection "
            "based on range of collection's items failed."
        )
        self.assertEqual(
            self.collection.cache_end_datetime,
            item_2nd_earliest_to_2nd_latest.properties_end_datetime,
            "Updating temporal extent (cache_end_datetime) of collection "
            "based on range of collection's items failed."
        )

        # changing the item, so that is does not have a range
        # but a single datetime value only
        item_2nd_earliest_to_2nd_latest.properties_start_datetime = None
        item_2nd_earliest_to_2nd_latest.properties_end_datetime = None
        item_2nd_earliest_to_2nd_latest.properties_datetime = start_earliest
        item_2nd_earliest_to_2nd_latest.save()
        self.collection.refresh_from_db()

        # currently there's only one item left in the collection
        # (item_2nd_earliest_to_2nd_latest). Hence, the collection's temporal
        # extent should be from this item's datetime to this item's datetime.
        # (an interval where both bounds are the same)

        self.assertEqual(
            self.collection.cache_start_datetime,
            item_2nd_earliest_to_2nd_latest.properties_datetime,
            "Updating temporal extent (cache_start_datetime) based on an item "
            "that was updated from having a range to a single datetime failed."
        )

        self.assertEqual(
            self.collection.cache_end_datetime,
            item_2nd_earliest_to_2nd_latest.properties_datetime,
            "Updating temporal extent (cache_end_datetime) based on an item "
            "that was updated from having a range to a single datetime failed."
        )

        # and back again from one single datetime to an explicit range
        # with start_ and end_datetimes:
        item_2nd_earliest_to_2nd_latest.properties_start_datetime = start_2nd_earliest
        item_2nd_earliest_to_2nd_latest.properties_end_datetime = end_2nd_latest
        item_2nd_earliest_to_2nd_latest.properties_datetime = None
        item_2nd_earliest_to_2nd_latest.save()
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.cache_start_datetime,
            item_2nd_earliest_to_2nd_latest.properties_start_datetime,
            "Updating temporal extent (cache_start_datetime) based on an item "
            "that was updated from a single datetime to a range failed."
        )

        self.assertEqual(
            self.collection.cache_end_datetime,
            item_2nd_earliest_to_2nd_latest.properties_end_datetime,
            "Updating temporal extent (cache_end_datetime) based on an item "
            "that was updated from a single datetime to a range failed."
        )

    def test_update_temporal_extent_datetime(self):
        '''
        test, if the collection's temporal extent is correctly updated, when
        and item is added. This test starts with items with a datetime value only.
        (no range). For testing, an item will be changed to have a range instead
        of a single datetime value.
        '''
        # create an item with a really early datetime and NO range
        earliest = utc_aware(datetime.strptime('0001-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
        _2nd_earliest = utc_aware(datetime.strptime('0010-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
        latest = utc_aware(datetime.strptime('9999-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
        _2nd_latest = utc_aware(datetime.strptime('9990-01-01T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))

        # create the 2nd oldest item with NO range
        item_2nd_earliest = Item.objects.create(
            collection=self.collection,
            item_name='2nd_earliest',
            properties_datetime=_2nd_earliest,
            properties_eo_gsd=None,
            properties_title="My Title",
        )
        db.create_item_links(item_2nd_earliest)
        item_2nd_earliest.save()
        self.collection.save()

        # create the 2nd latest item with NO range
        item_2nd_latest = Item.objects.create(
            collection=self.collection,
            item_name='2nd_latest',
            properties_datetime=_2nd_latest,
            properties_eo_gsd=None,
            properties_title="My Title",
        )
        db.create_item_links(item_2nd_earliest)
        item_2nd_latest.save()
        self.collection.save()

        # now with only the 2nd oldest and 2nd latest item inside the
        # collection, the collection's range should be equal to the two items
        self.assertEqual(
            self.collection.cache_start_datetime,
            item_2nd_earliest.properties_datetime,
            "Updating temporal extent (cache_start_datetime) of collection "
            "based on properties.datetime of the items failed. "
        )

        self.assertEqual(
            self.collection.cache_end_datetime,
            item_2nd_latest.properties_datetime,
            "Updating temporal extent (cache_end_datetime) of collection "
            "based on properties.datetime of the items failed. "
        )

        # adding even earlier and later item to the collection
        item_earliest = Item.objects.create(
            collection=self.collection,
            item_name='earliest',
            properties_datetime=earliest,
            properties_eo_gsd=None,
            properties_title="My Title",
        )
        db.create_item_links(item_earliest)
        item_earliest.save()
        self.collection.save()

        item_latest = Item.objects.create(
            collection=self.collection,
            item_name='latest',
            properties_datetime=latest,
            properties_eo_gsd=None,
            properties_title="My Title",
        )
        db.create_item_links(item_latest)
        item_latest.save()
        self.collection.save()

        # now the expected start_ and end_datetime of the collection should
        # updated to fit the oldest and latest item's dates:
        self.assertEqual(
            self.collection.cache_start_datetime,
            item_earliest.properties_datetime,
            "Updating temporal extent (cache_start_datetime) of collection "
            "based on properties.datetime of the items failed. "
        )

        self.assertEqual(
            self.collection.cache_end_datetime,
            item_latest.properties_datetime,
            "Updating temporal extent (cache_end_datetime) of collection "
            "based on properties.datetime of the items failed. "
        )

        # deleting the oldest and latest item again
        Item.objects.get(pk=item_earliest.pk).delete()
        Item.objects.get(pk=item_latest.pk).delete()
        self.collection.refresh_from_db()

        # Now the collection's range should be defined by the 2nd oldest
        # and 2nd latest item again:
        self.assertEqual(
            self.collection.cache_start_datetime,
            item_2nd_earliest.properties_datetime,
            "Updating temporal extent (cache_start_datetime) of collection "
            "based on properties.datetime of the items failed. "
        )

        self.assertEqual(
            self.collection.cache_end_datetime,
            item_2nd_latest.properties_datetime,
            "Updating temporal extent (cache_end_datetime) of collection "
            "based on properties.datetime of the items failed. "
        )

        # change the 2nd oldest item (which is the oldest currently) to have
        # a time range instead of a single datetime value:
        item_2nd_latest.properties_datetime = None
        item_2nd_latest.properties_start_datetime = earliest
        item_2nd_latest.properties_end_datetime = latest
        item_2nd_latest.save()
        self.collection.refresh_from_db()

        # now the collection's temporal extent should be defined by
        # item_2nd_latest.properties_start_ and _end_datetime values.
        self.assertEqual(
            self.collection.cache_start_datetime,
            item_2nd_latest.properties_start_datetime,
            "Updating temporal extent (cache_start_datetime) of collection "
            "based on an item, that was updated from having a single "
            "datetime value to a range failed."
        )

        self.assertEqual(
            self.collection.cache_end_datetime,
            item_2nd_latest.properties_end_datetime,
            "Updating temporal extent (cache_end_datetime) of collection "
            "based on an item, that was updated from having a single "
            "datetime value to a range failed."
        )
