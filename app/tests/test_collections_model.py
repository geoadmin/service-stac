import logging

from django.core.exceptions import ValidationError
from django.test import TestCase

from stac_api.models import Collection

from tests.data_factory import CollectionFactory

logger = logging.getLogger(__name__)


class CollectionsModelTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.collection = CollectionFactory().create_sample(db_create=True)

    def test_create_already_existing_collection(self):
        # try to create already existing collection twice
        with self.assertRaises(ValidationError, msg="Existing collection could be re-created."):
            collection = Collection(**self.collection.attributes)
            collection.full_clean()
            collection.save()

    def test_create_collection_invalid_name(self):
        # try to create a collection with invalid collection name
        with self.assertRaises(ValidationError, msg="Collection with invalid name was accepted."):
            collection_data = CollectionFactory().create_sample(sample="collection-invalid")
            collection = Collection(**collection_data.attributes)
            collection.full_clean()
            collection.save()

    def test_create_collection_missing_mandatory_fields(self):
        # try to create a collection with invalid collection name
        with self.assertRaises(
            ValidationError, msg="Collection with missing mandatory fields was accepted."
        ):
            CollectionFactory().create_sample(
                name="collection-missing-mandatory-fields",
                sample="collection-missing-mandatory-fields",
                db_create=True
            )

    def test_create_collection_invalid_links(self):
        # try to create a collection with invalid collection name
        with self.assertRaises(ValidationError, msg="Collection with invalid links was accepted."):
            CollectionFactory().create_sample(
                name="collection-invalid-links", sample="collection-invalid-links", db_create=True
            )

    def test_create_collection_invalid_providers(self):
        # try to create a collection with invalid collection name
        with self.assertRaises(
            ValidationError, msg="Collection with invalid providers was accepted."
        ):
            CollectionFactory().create_sample(sample="collection-invalid-providers", db_create=True)

    def test_create_collection_with_providers_and_links(self):
        # try to create a valid collection with providers and links. Should not raise any errors.
        CollectionFactory().create_sample(
            name="collection-links-providers", sample="collection-1", db_create=True
        )

    def test_create_collection_only_required_attributes(self):
        # try to create a valid collection with only the required attributes.
        # Should not raise any errors.
        CollectionFactory().create_sample(
            name="collection-links-providers",
            sample="collection-1",
            db_create=True,
            required_only=True
        )
