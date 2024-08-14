from django.core.exceptions import ValidationError
from django.test import TestCase

from stac_api.validators import MediaType
from stac_api.validators import get_media_type
from stac_api.validators import normalize_and_validate_media_type
from stac_api.validators import validate_content_encoding
from stac_api.validators import validate_item_properties_datetimes


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
