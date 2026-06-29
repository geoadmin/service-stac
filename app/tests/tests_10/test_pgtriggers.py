import logging

from parameterized import parameterized

from stac_api.models.collection import CollectionLink
from stac_api.models.general import Provider
from stac_api.models.item import AssetUpload
from stac_api.models.item import ItemLink

from tests.tests_10.base_test import StacBaseTransactionTestCase
from tests.tests_10.data_factory import Factory
from tests.tests_10.sample_data.asset_samples import FILE_CONTENT_1
from tests.utils import MockS3PerTestMixin

logger = logging.getLogger(__name__)


class PgTriggersFileSizeTestCase(MockS3PerTestMixin, StacBaseTransactionTestCase):

    def setUp(self):
        super().setUp()
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model
        self.item = self.factory.create_item_sample(collection=self.collection).model

        # Add a second item
        self.item2 = self.factory.create_item_sample(collection=self.collection,).model

    def test_pgtrigger_file_size(self):
        self.factory = Factory()
        file_size = len(FILE_CONTENT_1)

        self.assertEqual(self.collection.total_data_size, 0)
        self.assertEqual(self.item.total_data_size, 0)

        # check collection's and item's file size on asset update
        asset1 = self.factory.create_asset_sample(self.item, sample='asset-1', db_create=True)
        self.collection.refresh_from_db()
        self.assertEqual(self.collection.total_data_size, file_size)
        self.assertEqual(self.item.total_data_size, file_size)
        self.assertEqual(asset1.model.file_size, file_size)

        # check collection's and item's file size on asset update
        asset2 = self.factory.create_asset_sample(self.item, sample='asset-2', db_create=True)
        self.collection.refresh_from_db()
        self.assertEqual(self.collection.total_data_size, 2 * file_size)
        self.assertEqual(self.item.total_data_size, 2 * file_size)
        self.assertEqual(asset2.model.file_size, file_size)

        # check collection's and item's file size on adding an empty asset
        asset3 = self.factory.create_asset_sample(self.item, sample='asset-no-file', db_create=True)
        self.collection.refresh_from_db()

        self.assertEqual(self.collection.total_data_size, 2 * file_size)
        self.assertEqual(self.item.total_data_size, 2 * file_size)
        self.assertEqual(asset3.model.file_size, 0)

        # check collection's and item's file size when updating asset of another item
        asset4 = self.factory.create_asset_sample(self.item2, sample='asset-2', db_create=True)
        self.collection.refresh_from_db()

        self.assertEqual(
            self.collection.total_data_size,
            3 * file_size,
        )
        self.assertEqual(self.item.total_data_size, 2 * file_size)
        self.assertEqual(self.item2.total_data_size, file_size)

        # check collection's and item's file size when deleting asset
        asset1.model.delete()
        self.item.refresh_from_db()
        self.collection.refresh_from_db()

        self.assertEqual(self.collection.total_data_size, 2 * file_size)
        self.assertEqual(self.item.total_data_size, 1 * file_size)


class PgTriggersUpdated(MockS3PerTestMixin, StacBaseTransactionTestCase):

    def setUp(self):
        super().setUp()
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample(db_create=True).model
        self.collection_asset = self.factory.create_collection_asset_sample(
            collection=self.collection, db_create=True
        ).model
        self.item = self.factory.create_item_sample(
            collection=self.collection, db_create=True
        ).model
        self.asset = self.factory.create_asset_sample(
            self.item, sample='asset-1', db_create=True
        ).model
        self.collection_link = self.create_object(
            CollectionLink,
            collection=self.collection,
            href='https://example.com/collection/link/test',
            rel='whatever',
        )
        self.provider = self.create_object(
            Provider,
            collection=self.collection,
            name='Totally legit provider name',
        )
        self.item_link = self.create_object(
            ItemLink,
            item=self.item,
            href='https://example.com/item/link/test',
            rel='whatever',
        )

    def create_object(self, obj_type, **kwargs):
        obj = obj_type(**kwargs)
        obj.full_clean()
        obj.save()
        obj.refresh_from_db()
        return obj

    @parameterized.expand([
        ('asset', 'asset', 'checksum_multihash', True),
        ('asset', 'asset', 'description', False),
        ('item', 'item', 'name', False),
        ('collection', 'collection', 'name', False),
        ('collection_asset', 'collection_asset', 'name', False),
        ('collection_asset', 'collection_asset', 'checksum_multihash', True),
        ('asset', 'item', 'checksum_multihash', True),
        ('asset', 'item', 'title', False),
        ('item', 'collection', 'name', False),
        ('collection_asset', 'collection', 'checksum_multihash', True),
        ('collection_asset', 'collection', 'name', False),
        ('collection_link', 'collection', 'title', False),
        ('item_link', 'item', 'title', False),
        ('provider', 'collection', 'name', False),
    ])
    def test_timestamp_updated(self, source_name, destination_name, field_name, expect_update):
        destination = getattr(self, destination_name)
        destination.refresh_from_db()
        source = getattr(self, source_name)
        source.refresh_from_db()

        prev_etag = destination.etag
        prev_mtime = destination.updated
        setattr(source, field_name, 'new value')
        source.save()
        destination.refresh_from_db()

        self.assertNotEqual(destination.etag, prev_etag)
        if expect_update:
            self.assertGreater(destination.updated, prev_mtime)
        else:
            self.assertEqual(destination.updated, prev_mtime)


class PgTriggerAssetUploads(MockS3PerTestMixin, StacBaseTransactionTestCase):

    def setUp(self):
        super().setUp()
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample(db_create=True).model
        self.collection_asset = self.factory.create_collection_asset_sample(
            collection=self.collection, db_create=True
        ).model
        self.item = self.factory.create_item_sample(
            collection=self.collection, db_create=True
        ).model
        self.asset = self.factory.create_asset_sample(
            self.item, sample='asset-1', db_create=True
        ).model
        self.asset_upload = AssetUpload(
            asset=self.asset,
            upload_id=42,
            checksum_multihash=b'some hash',
            md5_parts=['totally a valid md5'],
            number_parts=1,
        )
        self.asset_upload.full_clean()
        self.asset_upload.save()
        self.asset_upload.refresh_from_db()

    def test_etag_updated(self):
        prev_etag = self.asset_upload.etag
        self.asset_upload.status = AssetUpload.Status.ABORTED
        self.asset_upload.save()
        self.asset_upload.refresh_from_db()
        self.assertNotEqual(self.asset_upload.etag, prev_etag)
