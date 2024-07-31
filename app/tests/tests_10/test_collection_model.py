import logging
from time import sleep

from django.core.exceptions import ValidationError

from stac_api.models import Collection

from tests.tests_10.base_test import StacBaseTransactionTestCase
from tests.tests_10.data_factory import Factory
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)


# Here we need to use TransactionTestCase due to the pgtrigger, in a normal
# test case we cannot test effect of pgtrigger.
class CollectionsModelTestCase(StacBaseTransactionTestCase):

    @mock_s3_asset_file
    def setUp(self):
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample(db_create=True)

    def test_create_already_existing_collection(self):
        # try to create already existing collection twice
        with self.assertRaises(ValidationError, msg="Existing collection could be re-created."):
            collection = Collection(**self.collection.attributes)
            collection.full_clean()
            collection.save()

    def test_create_collection_invalid_name(self):
        # try to create a collection with invalid collection name
        with self.assertRaises(ValidationError, msg="Collection with invalid name was accepted."):
            self.factory.create_collection_sample(
                name="invalid name", sample="collection-invalid", db_create=True
            )

    def test_create_collection_missing_mandatory_fields(self):
        # try to create a collection with invalid collection name
        with self.assertRaises(
            ValidationError, msg="Collection with missing mandatory fields was accepted."
        ):
            self.factory.create_collection_sample(
                name="collection-missing-mandatory-fields",
                sample="collection-missing-mandatory-fields",
                db_create=True
            )

    def test_create_collection_invalid_links(self):
        # try to create a collection with invalid collection name
        with self.assertRaises(ValidationError, msg="Collection with invalid links was accepted."):
            self.factory.create_collection_sample(
                name="collection-invalid-links", sample="collection-invalid-links", db_create=True
            )

    def test_create_collection_multiple_links(self):
        # try to create a collection with multiple links of the same type.
        # Should not raise any errors.
        self.factory.create_collection_sample(
            name="collection-multiple-links", sample="collection-multiple-links", db_create=True
        )

    def test_create_collection_invalid_providers(self):
        # try to create a collection with invalid collection name
        with self.assertRaises(
            ValidationError, msg="Collection with invalid providers was accepted."
        ):
            self.factory.create_collection_sample(
                sample="collection-invalid-providers", db_create=True
            )

    def test_create_collection_with_providers_and_links(self):
        # try to create a valid collection with providers and links. Should not raise any errors.
        self.factory.create_collection_sample(
            name="collection-links-providers", sample="collection-1", db_create=True
        )

    def test_create_collection_only_required_attributes(self):
        # try to create a valid collection with only the required attributes.
        # Should not raise any errors.
        self.factory.create_collection_sample(
            name="collection-required-only",
            sample="collection-1",
            db_create=True,
            required_only=True
        )

    def test_collection_update_on_item_write_operations(self):
        # assert that collection's updated property is updated when an item is
        # added to the collection, this item is updated and this item is deleted

        # check collection's update on item insertion
        initial_last_modified = self.collection.model.updated
        sleep(0.01)
        item = self.factory.create_item_sample(
            self.collection.model, sample='item-1', db_create=True
        )
        self.collection.model.refresh_from_db()
        self.assertGreater(
            self.collection.model.updated,
            initial_last_modified,
            msg="Collection's updated property was not updated on item insert"
        )

        # check collection's update on item update
        initial_last_modified = self.collection.model.updated
        sleep(0.01)
        item.model.properties_title = f"new_{item.model.properties_title}"
        item.model.full_clean()
        item.model.save()
        self.collection.model.refresh_from_db()
        self.assertGreater(
            self.collection.model.updated,
            initial_last_modified,
            msg="Collection's updated property was not updated on item update"
        )

        # check collection's update on item deletion
        initial_last_modified = self.collection.model.updated
        sleep(0.01)
        item.model.delete()
        self.collection.model.refresh_from_db()
        self.assertGreater(
            self.collection.model.updated,
            initial_last_modified,
            msg="Collection's updated property was not updated on item deletion"
        )

    def test_collection_update_on_asset_write_operations(self):
        # assert that collection's updated property is updated when an asset is
        # added to an item of the collection, this asset is updated and this asset is deleted

        # check collection's update on asset insertion
        item = self.factory.create_item_sample(
            self.collection.model, sample='item-1', db_create=True
        )
        initial_last_modified = self.collection.model.updated
        sleep(0.01)
        asset = self.factory.create_asset_sample(item=item.model, sample='asset-1', db_create=True)
        self.collection.model.refresh_from_db()
        self.assertGreater(
            self.collection.model.updated,
            initial_last_modified,
            msg="Collection's updated property was not updated on asset insert"
        )

        # check collection's update on asset update
        initial_last_modified = self.collection.model.updated
        sleep(0.01)
        asset.model.title = f"new-{asset.model.title}"
        asset.model.full_clean()
        asset.model.save()
        self.collection.model.refresh_from_db()
        self.assertGreater(
            self.collection.model.updated,
            initial_last_modified,
            msg="Collection's updated property was not updated on asset update"
        )

        # check collection's update on asset deletion
        initial_last_modified = self.collection.model.updated
        sleep(0.01)
        asset.model.delete()
        self.collection.model.refresh_from_db()
        self.assertGreater(
            self.collection.model.updated,
            initial_last_modified,
            msg="Collection's updated property was not updated on asset deletion"
        )
