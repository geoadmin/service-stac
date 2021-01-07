from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase

from rest_framework.exceptions import ValidationError

from stac_api.validators import validate_item_properties_datetimes_dependencies
from stac_api.validators_serializer import validate_asset_href_path

from tests.data_factory import Factory


class TestValidators(TestCase):

    def test_validate_asset_href_path(self):
        factory = Factory()
        collection = factory.create_collection_sample(name='collection-test').model
        item = factory.create_item_sample(collection=collection, name='item-test').model
        validate_asset_href_path(item, 'asset-test', 'collection-test/item-test/asset-test')

        with self.settings(AWS_S3_CUSTOM_DOMAIN='new-domain'):
            validate_asset_href_path(item, 'asset-test', 'collection-test/item-test/asset-test')

        with self.settings(AWS_S3_CUSTOM_DOMAIN='new-domain/with-prefix/'):
            validate_asset_href_path(
                item, 'asset-test', 'with-prefix/collection-test/item-test/asset-test'
            )

        with self.settings(AWS_S3_CUSTOM_DOMAIN='//new-domain/with-prefix'):
            validate_asset_href_path(
                item, 'asset-test', 'with-prefix/collection-test/item-test/asset-test'
            )

        with self.settings(AWS_S3_CUSTOM_DOMAIN='//new domain/with-prefix'):
            validate_asset_href_path(
                item, 'asset-test', 'with-prefix/collection-test/item-test/asset-test'
            )

        with self.assertRaises(
            ValidationError, msg="Invalid Asset href path did not raises ValidationError"
        ):
            validate_asset_href_path(item, 'asset-test', 'asset-test')
            validate_asset_href_path(item, 'asset-test', 'item-test/asset-test')
            validate_asset_href_path(item, 'asset-test', 'collection-test/item-test/asset-test')
            validate_asset_href_path(
                item, 'asset-test', '/service-stac-local/collection-test/item-test/asset-test'
            )

    def test_validate_function_invalid_datetime_string(self):
        with self.assertRaises(DjangoValidationError):
            properties_datetime = None
            properties_start_datetime = "2001-22-66T08:00:00+00:00"
            properties_end_datetime = "2001-11-11T08:00:00+00:00"
            validate_item_properties_datetimes_dependencies(
                properties_datetime, properties_start_datetime, properties_end_datetime
            )
