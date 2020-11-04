import logging
from datetime import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase

from stac_api.models import Item
from stac_api.utils import utc_aware

import tests.database as db

logger = logging.getLogger(__name__)


class ItemsModelTestCase(TestCase):

    def setUp(self):
        self.collection = db.create_collection('collection-1')

    def test_item_create_model(self):
        item = Item.objects.create(
            collection=self.collection,
            item_name='item-1',
            properties_datetime=utc_aware(datetime.utcnow())
        )
        item.save()
        self.assertEqual('item-1', item.item_name)

    def test_item_create_model_invalid_datetime(self):
        with self.assertRaises(ValidationError, msg="no datetime is invalid"):
            item = Item.objects.create(collection=self.collection, item_name='item-1')
            item.clean()

        with self.assertRaises(ValidationError, msg="only start_datetime is invalid"):
            item = Item.objects.create(
                collection=self.collection,
                item_name='item-2',
                properties_start_datetime=utc_aware(datetime.utcnow())
            )
            item.clean()

        with self.assertRaises(ValidationError, msg="only end_datetime is invalid"):
            item = Item.objects.create(
                collection=self.collection,
                item_name='item-3',
                properties_end_datetime=utc_aware(datetime.utcnow())
            )
            item.clean()

        with self.assertRaises(ValidationError, msg="datetime is not allowed with start_datetime"):
            item = Item.objects.create(
                collection=self.collection,
                item_name='item-4',
                properties_datetime=utc_aware(datetime.utcnow()),
                properties_start_datetime=utc_aware(datetime.utcnow()),
                properties_end_datetime=utc_aware(datetime.utcnow())
            )
            item.clean()

        with self.assertRaises(ValidationError):
            item = Item.objects.create(
                collection=self.collection, item_name='item-1', properties_datetime='asd'
            )

        with self.assertRaises(ValidationError):
            item = Item.objects.create(
                collection=self.collection, item_name='item-4', properties_start_datetime='asd'
            )

        with self.assertRaises(ValidationError):
            item = Item.objects.create(
                collection=self.collection, item_name='item-1', properties_end_datetime='asd'
            )
