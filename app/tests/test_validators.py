from django.test import TestCase

from rest_framework.exceptions import ValidationError

from stac_api.validators_serializer import validate_asset_href_path

from tests.database import create_collection
from tests.database import create_item


class TestValidators(TestCase):

    def test_validate_asset_href_path(self):
        collection = create_collection('collection-test')
        item = create_item(collection, 'item-test')
        validate_asset_href_path(
            item, 'asset-test', 'service-stac-local/collection-test/item-test/asset-test'
        )

        # Override the AWS_S3_CUSTOM_DOMAIN setting
        with self.settings(AWS_S3_CUSTOM_DOMAIN=''):
            validate_asset_href_path(item, 'asset-test', 'collection-test/item-test/asset-test')

        with self.settings(AWS_S3_CUSTOM_DOMAIN=None):
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
