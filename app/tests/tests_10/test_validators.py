from parameterized import parameterized

from django.core.exceptions import ValidationError
from django.test import TestCase

from stac_api.validators import MediaType
from stac_api.validators import _validate_href_configured_pattern
from stac_api.validators import _validate_href_scheme
from stac_api.validators import get_media_type
from stac_api.validators import normalize_and_validate_media_type
from stac_api.validators import validate_content_encoding
from stac_api.validators import validate_item_properties_datetimes

from tests.tests_10.data_factory import Factory


class TestValidators(TestCase):

    def test_validate_function_invalid_datetime_string(self):
        with self.assertRaises(ValidationError):
            properties_datetime = None
            properties_start_datetime = "2001-22-66T08:00:00+00:00"
            properties_end_datetime = "2001-11-11T08:00:00+00:00"
            properties_expires = None
            validate_item_properties_datetimes(
                properties_datetime,
                properties_start_datetime,
                properties_end_datetime,
                properties_expires
            )

    def test_validate_invalid_content_encoding(self):
        for value in [
            '', 'gzip ', 'hello', 'gzip, gzip', 'gzipp', 'gzip, hello', 'gzip hello', 'gzip br'
        ]:
            with self.subTest(msg=f"check invalid content_encoding: {value}"):
                with self.assertRaises(
                    ValidationError, msg=f'Validation error for "{value}" not raised'
                ):
                    validate_content_encoding(value)

    def test_validate_valid_content_encoding(self):
        for value in [
            'gzip',
            'br',
            # 'gzip, br',
            # 'br, gzip',
            # 'compress',
            # 'compress, br, gzip, deflate',
            # 'gzip,br',
            # 'gzip,     br'
        ]:
            with self.subTest(msg=f"check invalid content_encoding: {value}"):
                try:
                    validate_content_encoding(value)
                except ValidationError as err:
                    self.fail(f'Validation for valid content_encoding "{value}" failed: {err}')


class TestMediaTypeValidators(TestCase):

    def test_normalized_media_type_str(self):
        media_type_str = 'image/tiff; application=geotiff; profile=cloud-optimized'
        media_type = MediaType(
            'image/tiff; application=geotiff; profile=cloud-optimized',
            'Cloud Optimized GeoTIFF (COG)', ['.tiff', '.tif']
        )

        self.assertEqual(normalize_and_validate_media_type(media_type_str), media_type[0])
        self.assertEqual(normalize_and_validate_media_type(media_type_str), media_type_str)
        self.assertTupleEqual(get_media_type(media_type_str), media_type)

    def test_not_normalized_media_type_str(self):
        media_type_str = 'image/TIFF;profile=cloud-optimized ; Application=geotiff'
        media_type = MediaType(
            'image/tiff; application=geotiff; profile=cloud-optimized',
            'Cloud Optimized GeoTIFF (COG)', ['.tiff', '.tif']
        )

        self.assertEqual(normalize_and_validate_media_type(media_type_str), media_type[0])
        self.assertTupleEqual(get_media_type(media_type[0]), media_type)
        self.assertRaises(KeyError, get_media_type, media_type_str)

    def test_malformed_or_invalid_media_type_strings(self):
        media_type_strings = [
            # Malformed media types
            'image/"TIFF";profile="cloud-optimized" ; Application=geotiff',
            'image/TIFF;profile=cloud-optimized Application=geotiff',
            'image/TIFF;profile="cloud-optimized" ; Application = geotiff',
            'image/tiff; "profile=cloud-optimized" ; Application=geotiff',
            'image/tiff; application=Geotiff; profile=cloud-optimized',
            # Valid according to the norm, but we do not accept quotes
            'image/TIFF;profile="cloud-optimized" ; Application=geotiff',
            # Valid media type, but not part of the list of accepted media types
            'audio/mpeg'
        ]
        for media_type_str in media_type_strings:
            self.assertRaises(ValidationError, normalize_and_validate_media_type, media_type_str)
            self.assertRaises(KeyError, get_media_type, media_type_str)


class TestExternalAssetValidators(TestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample().model

    @parameterized.expand([
        (['https://test-domain.test'], 'https://test-domain.test/collection/test.jpg', True),
        (['https://test-domain'], 'https://test-domain.test/collection/test.jpg', True),
        (['https://test-domaine', 'https://test-domain'],
         'https://test-domain.test/collection/test.jpg',
         True),  # trying to keep the formatting stable
        (['https://test-domain.test/collection'],
         'https://test-domain.test/collection/test.jpg',
         True),  # trying to keep the formatting stable here
        (['https://test-domain.tst', 'https://something-else.ch'],
         'https://test-domain.test/collection/test.jpg',
         False),
        (['http://test-domain.test'], 'https://test-domain.tst/collection/test.jpg', False),
        (['https://test-domain.test'], 'http://test-domain.test/collection/test.jpg', False)
    ])
    def test_create_external_asset_with_collection_pattern(self, patterns, href, result):
        collection = self.collection

        collection.external_asset_whitelist = patterns
        collection.save()

        if result:
            # pylint: disable=W0212:protected-access
            _validate_href_configured_pattern(href, collection)
        else:
            with self.assertRaises(ValidationError):
                # pylint: disable=W0212:protected-access
                _validate_href_configured_pattern(href, collection)

    def test_scheme_validator(self):
        with self.settings(DISALLOWED_EXTERNAL_ASSET_SCHEME=['http']):
            collection = self.collection

            url = 'http://map.geo.admin.ch'
            with self.assertRaises(ValidationError):
                _validate_href_scheme(url, collection)
