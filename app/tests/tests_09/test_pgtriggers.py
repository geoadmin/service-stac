import logging

from tests.tests_09.base_test import StacBaseTransactionTestCase
from tests.tests_09.data_factory import Factory
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)


class PgTriggersUpdateIntervalTestCase(StacBaseTransactionTestCase):

    @mock_s3_asset_file
    def setUp(self):
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model

        # Add a second collection with assets
        self.collection2 = self.factory.create_collection_sample().model
        self.item2 = self.factory.create_item_sample(collection=self.collection2,).model
        self.assets2 = [
            self.factory.create_asset_sample(item=self.item2, update_interval=1).model,
            self.factory.create_asset_sample(item=self.item2, update_interval=-1).model,
            self.factory.create_asset_sample(item=self.item2, update_interval=1000).model,
        ]

    def test_pgtrigger_item_update_interval(self):
        self.assertEqual(self.item.update_interval, -1)
        asset1 = self.factory.create_asset_sample(item=self.item, update_interval=60).model
        asset2 = self.factory.create_asset_sample(item=self.item).model  # default -1
        asset3 = self.factory.create_asset_sample(item=self.item, update_interval=10).model
        self.item.refresh_from_db()
        self.assertEqual(self.item.update_interval, 10)

        asset3.delete()
        self.item.refresh_from_db()
        self.assertEqual(self.item.update_interval, 60)

        asset4 = self.factory.create_asset_sample(item=self.item, update_interval=0).model
        self.item.refresh_from_db()
        self.assertEqual(self.item.update_interval, 0)

    def test_pgtrigger_collection_update_interval(self):
        self.assertEqual(self.item.update_interval, -1)
        self.assertEqual(self.collection.update_interval, -1)
        asset1 = self.factory.create_asset_sample(item=self.item, update_interval=60).model
        asset2 = self.factory.create_asset_sample(item=self.item).model  # default -1
        asset3 = self.factory.create_asset_sample(item=self.item, update_interval=10).model
        self.collection.refresh_from_db()
        self.assertEqual(self.collection.update_interval, 10)

        # add new item with assets
        item2 = self.factory.create_item_sample(collection=self.collection).model
        self.collection.refresh_from_db()
        self.assertEqual(self.collection.update_interval, 10)

        asset1 = self.factory.create_asset_sample(item=item2, update_interval=600).model
        asset2 = self.factory.create_asset_sample(item=item2).model  # default -1
        asset3 = self.factory.create_asset_sample(item=item2, update_interval=2).model

        self.collection.refresh_from_db()
        self.assertEqual(self.collection.update_interval, 2)

        asset4 = self.factory.create_asset_sample(item=item2, update_interval=0).model
        self.collection.refresh_from_db()
        self.assertEqual(self.collection.update_interval, 0)
