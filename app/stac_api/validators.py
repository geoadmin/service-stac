import logging
import re
from collections import namedtuple
from datetime import datetime
from urllib.parse import urlparse

import multihash
import requests
from multihash.constants import CODE_HASHES
from multihash.constants import HASH_CODES

from django.conf import settings
from django.contrib.gis.gdal.error import GDALException
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos.error import GEOSException
from django.core import exceptions
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.regex_helper import _lazy_re_compile
from django.utils.translation import gettext_lazy as _

from stac_api.utils import fromisoformat
from stac_api.utils import geometry_from_bbox
from stac_api.utils import is_valid_b64

logger = logging.getLogger(__name__)

MediaType = namedtuple('MediaType', 'media_type_str, description, extensions')
'''A MediaType is a tuple containing information about a media type that is accepted for asset data

Attributes:
    media_type_str: str
        A media type string. It should already be normalized according to the rules described in the
        "normalize_and_validate_media_type" function
    description: str
        A human readable description
    extensions: [str]
        A list of allowed extensions. Each string in this list should start with a dot.

NOTE: This list needs to be kept in sync with the openapi spec in ./spec/transaction/tags.yaml
'''
MEDIA_TYPES = [
    MediaType(
        'application/vnd.apache.parquet',
        'Apache Parquet column-oriented data file format', ['.parquet']
    ),
    MediaType('application/x.ascii-grid+zip', 'Zipped ESRI ASCII raster format (.asc)', ['.zip']),
    MediaType('application/x.ascii-xyz+zip', 'Zipped XYZ (.xyz)', ['.zip']),
    MediaType('application/x.e00+zip', 'Zipped e00', ['.zip']),
    MediaType('application/x.geotiff+zip', 'Zipped GeoTIFF', ['.zip']),
    MediaType('image/tiff; application=geotiff', 'GeoTIFF', ['.tiff', '.tif']),
    MediaType('application/x.tiff+zip', 'Zipped TIFF', ['.zip']),
    MediaType('application/x.png+zip', 'Zipped PNG', ['.zip']),
    MediaType('application/x.jpeg+zip', 'Zipped JPEG', ['.zip']),
    MediaType('application/vnd.google-earth.kml+xml', 'KML', ['.kml']),
    MediaType('application/vnd.google-earth.kmz', 'Zipped KML', ['.kmz']),
    MediaType('application/x.dxf+zip', 'Zipped DXF', ['.zip']),
    MediaType('application/gml+xml', 'GML', ['.gml', '.xml']),
    MediaType('application/x.gml+zip', 'Zipped GML', ['.zip']),
    MediaType('application/vnd.las', 'LIDAR', ['.las']),
    MediaType('application/vnd.laszip', 'Zipped LIDAR', ['.laz', '.zip']),
    MediaType('application/x.vnd.las+zip', 'Zipped LAS', ['.zip']),
    MediaType('application/vnd.laszip+copc', 'Cloud Optimized Point Cloud (COPC)', ['.zip']),
    MediaType('application/x.shapefile+zip', 'Zipped Shapefile', ['.zip']),
    MediaType('application/x.filegdb+zip', 'Zipped File Geodatabase', ['.zip']),
    MediaType('application/x.filegdbp+zip', 'Zipped File Geodatabase (ArcGIS Pro)', ['.zip']),
    MediaType('application/x.ms-access+zip', 'Zipped Personal Geodatabase', ['.zip']),
    MediaType('application/x.ms-excel+zip', 'Zipped Excel', ['.zip']),
    MediaType('application/x.tab+zip', 'Zipped Mapinfo-TAB', ['.zip']),
    MediaType('application/x.tab-raster+zip', 'Zipped Mapinfo-Raster-TAB', ['.zip']),
    MediaType('application/x.csv+zip', 'Zipped CSV', ['.zip']),
    MediaType('text/csv', 'CSV', ['.csv']),
    MediaType('application/geopackage+sqlite3', 'Geopackage', ['.gpkg']),
    MediaType('application/x.geopackage+zip', 'Zipped Geopackage', ['.zip']),
    MediaType('application/geo+json', 'GeoJSON', ['.json', '.geojson']),
    MediaType('application/x.geojson+zip', 'Zipped GeoJSON', ['.zip']),
    MediaType('application/x.interlis; version=2.3', 'Interlis 2', ['.xtf', '.xml']),
    MediaType('application/x.interlis+zip; version=2.3', 'Zipped XTF (2.3)', ['.zip']),
    MediaType('application/x.interlis; version=2.4', 'Interlis 2', ['.xtf', '.xml']),
    MediaType('application/x.interlis+zip; version=2.4', 'Zipped XTF (2.4)', ['.zip']),
    MediaType('application/x.interlis; version=1', 'Interlis 1', ['.itf']),
    MediaType('application/x.interlis+zip; version=1', 'Zipped ITF', ['.zip']),
    MediaType(
        'image/tiff; application=geotiff; profile=cloud-optimized',
        'Cloud Optimized GeoTIFF (COG)', ['.tiff', '.tif']
    ),
    MediaType('application/pdf', 'PDF', ['.pdf']),
    MediaType('application/x.pdf+zip', 'Zipped PDF', ['.zip']),
    MediaType('application/json', 'JSON', ['.json']),
    MediaType('application/x.json+zip', 'Zipped JSON', ['.zip']),
    MediaType('application/x-netcdf', 'NetCDF', ['.nc']),
    MediaType('application/x.netcdf+zip', 'Zipped NetCDF', ['.zip']),
    MediaType('application/xml', 'XML', ['.xml']),
    MediaType('application/x.xml+zip', 'Zipped XML', ['.zip']),
    MediaType('application/vnd.mapbox-vector-tile', 'mbtiles', ['.mbtiles']),
    MediaType('text/plain', 'Text', ['.txt']),
    MediaType('text/x.plain+zip', 'Zipped text', ['.zip']),
    MediaType('application/x.dwg+zip', 'Zipped DWG', ['.zip']),
    MediaType('application/zip', 'Generic Zip File', ['.zip']),
    MediaType('image/tiff', 'TIFF', ['.tiff', '.tif']),
    MediaType('image/jpeg', 'JPEG', ['.jpeg', '.jpg']),
    MediaType('image/png', 'PNG', ['.png']),
    MediaType('application/vnd.sqlite3', 'sqlite', ['.sqlite']),
]

MT_VAR = "[0-9A-Za-z!#$%&'*+.^_`|~-]+"
MEDIA_TYPE_ARGUMENT = re.compile(f"[ \t]*;[ \t]*({MT_VAR})=({MT_VAR})")
MEDIA_TYPE_PATTERN = re.compile(f"^({MT_VAR}/{MT_VAR})((?:[ \t]*;[ \t]*{MT_VAR}={MT_VAR})*)$")


def normalize_and_validate_media_type(media_type_str):
    '''
    Normalizes the media type string and validate it.

    Normalizes the media type string and check that the media type string is one of the media types
    accepted by the application.

    To simplify comparasion, media type strings are normalized as soon as possible, and only
    normalized strings can be saved in the database.

    This list explains how the variants accepted by the norm are mapped to their respective
    normalized form (variants accepted by the norm => normalized form)
    - Types, subtypes and parameter names are case insensitive. => They are in lowercase
    - Parameter values may be case sensitive => They are kept unchanged
    - Order of the parameters is not important => They are ordered alphabetically
    - no whitespace around "=" allowed. Whitespace only allowed around the ";" parameter separator
      => No whitespaces before the semicolon, one whitespace after
    - Parameter values are allowed to be quoted => Here we derogate from the norm to keep it simple.
      Quoted parameters are considered malformed.

    Args:
        media_type_str: str
            The media type string to normalize and validate

    Returns:
        The normalized media type string

    Raises:
        ValidationError:
            Media type string is either malformed or not one of the accepted media types.
    '''
    try:
        # May throw AttributeError on failed fullmatch => Malformed media type
        media_type, args = MEDIA_TYPE_PATTERN.fullmatch(media_type_str).groups()
        normalized_str = media_type.lower() + ''.join(
            sorted(map(lambda x: f'; {x[0].lower()}={x[1]}', MEDIA_TYPE_ARGUMENT.findall(args)))
        )
        # May throw KeyError=> valid media type, but type is not in the list of accepted media types
        return get_media_type(normalized_str).media_type_str
    except (AttributeError, KeyError) as ex:
        logger.error("Invalid media_type %s", media_type_str)
        raise ValidationError(
            _('Invalid media type "%(media_type)s"'),
            params={'media_type': media_type_str},
            code='invalid'
        ) from ex


MEDIA_TYPES_EXTENSIONS = frozenset([ext for media_type in MEDIA_TYPES for ext in media_type[2]])
_MEDIA_TYPES_BY_STR = {media[0]: media for media in MEDIA_TYPES}


def get_media_type(media_type_str):
    '''Return a MediaType or raise a KeyError if no MediaType exists for the given string
    '''
    return _MEDIA_TYPES_BY_STR[media_type_str]


def validate_media_type(media_type_str):
    '''Like "get_media_type", but raise a ValidationError instead of a KeyError
    '''
    try:
        return get_media_type(media_type_str)
    except KeyError as ex:
        raise ValidationError(
            _('Invalid media type "%(media_type)s"'),
            params={'media_type': media_type_str},
            code='invalid'
        ) from ex


def validate_name(name):
    '''Validate name used in URL
    '''
    if not re.match(r'^[0-9a-z-_.]+$', name):
        logger.error('Invalid name %s, only the following characters are allowed: 0-9a-z-_.', name)
        raise ValidationError(
            _('Invalid id, only the following characters are allowed: 0-9a-z-_.'),
            code='invalid'
        )


def validate_asset_name(name):
    '''Validate Asset name used in URL
    '''
    if not name:
        logger.error('Invalid asset name, must not be empty')
        raise ValidationError(_("Invalid id must not be empty"), code='missing')
    validate_name(name)
    ext = name.rsplit('.', maxsplit=1)[-1]
    if f'.{ext}' not in MEDIA_TYPES_EXTENSIONS:
        logger.error(
            'Invalid name %s extension %s, name must ends with a valid file extension', name, ext
        )
        raise ValidationError(
            _("Invalid id extension '.%(ext)s', id must have a valid file extension"),
            params={'ext': ext},
            code='invalid'
        )


def validate_asset_name_with_media_type(name, media_type):
    '''Validate Asset name against the media type

    Args:
        name: string
            Name of the asset
        media_type: MediaType | str
            The media type object or string that should be matched by the asset name
    '''
    if isinstance(media_type, str):
        media_type = get_media_type(media_type)
    ext = f".{name.rsplit('.', maxsplit=1)[-1]}"
    if ext not in media_type.extensions:
        logger.error(
            "Invalid name %s extension %s, don't match the media type %s",
            name,
            ext,
            media_type,
        )
        raise ValidationError(
            _("Invalid id extension '%(ext)s', id must match its media type %(media_type)s"),
            params={'ext': ext, 'media_type': media_type.media_type_str},
            code='invalid'
        )


def validate_geoadmin_variant(variant):
    '''Validate geoadmin:variant, it should not have special characters

    The only special character allowed is a space in between regular characters

    Args:
        variant: string
            The string to validate
    Raise:
        ValidationError: When the string does not match the re.match
    '''
    if not re.match('^([a-zA-Z0-9]+\\s)*[a-zA-Z0-9]+$', variant):
        logger.error(
            "Invalid geoadmin:variant property \"%s\", special characters not allowed." \
            "One space in between is the exception.",
            variant
        )
        raise ValidationError(
            _('Invalid geoadmin:variant "%(variant)s", '
              'special characters beside one space are not allowed'),
            params={'variant': variant},
            code="invalid"
        )


def validate_eo_gsd(value):
    '''Validate gsd

    Args:
        value: float
            The value to validate
    Raise:
        ValidationError: When the value is not valid
    '''
    if value <= 0:
        logger.error("Invalid gsd property \"%f\", value must be > 0", value)
        raise ValidationError(
            _('Invalid gsd "%(eo_gsd)f", '
              'value must be a positive number bigger than 0'),
            params={'eo_gsd': value},
            code="invalid"
        )


def validate_link_rel(value):
    invalid_rel = [
        'self',
        'root',
        'parent',
        'items',
        'collection',
        'service-desc',
        'service-doc',
        'search',
        'conformance'
    ]
    if value in invalid_rel:
        logger.error("Link rel attribute %s is not allowed, it is a reserved attribute", value)
        raise ValidationError(
            _('Invalid rel attribute, must not be in %(invalid_rel)s'),
            params={'invalid_rel': invalid_rel},
            code="invalid"
        )


def validate_text_to_geometry(text_geometry):
    '''
    https://jira.swisstopo.ch/browse/BGDIINF_SB-1650
    A validator function that tests, if a text can be transformed to a geometry.
    The text is either a bbox or WKT.

    an extent in either WGS84 or LV95, in the form "(xmin, ymin, xmax, ymax)" where x is easting
    a WKT defintion of a polygon in the form POLYGON ((30 10, 40 40, 20 40, 10 20, 30 10))

    Args:
        text_geometry: The text to be transformed into a geometry
    Returns:
        A GEOSGeometry
    Raises:
        ValidationError: About that the text_geometry is not valid
    '''
    errors = []
    # is the input WKT
    try:
        geos_geometry = GEOSGeometry(text_geometry)
        validate_geometry(geos_geometry, apply_transform=True)
        return geos_geometry
    except (ValueError, ValidationError, IndexError, GDALException, GEOSException) as error:
        message = "The text as WKT could not be transformed into a geometry: %(error)s"
        params = {'error': error}
        logger.warning(message, params)
        errors.append(ValidationError(_(message), params=params, code='invalid'))
    # is the input a bbox
    try:
        text_geometry = text_geometry.replace('(', '')
        text_geometry = text_geometry.replace(')', '')
        return validate_geometry(geometry_from_bbox(text_geometry), apply_transform=True)
    except (ValueError, ValidationError, IndexError, GDALException) as error:
        message = "The text as bbox could not be transformed into a geometry: %(error)s"
        params = {'error': error}
        logger.error(message, params)
        errors.append(ValidationError(_(message), params=params, code='invalid'))
        raise ValidationError(errors) from None


def validate_geometry(geometry, apply_transform=False):
    '''
    A validator function that ensures, that only valid
    geometries are stored.
    Args:
         geometry: The geometry that will be validated

    Returns:
        The geometry, when tested valid

    Raises:
        ValidateionError: About that the geometry is not valid
    '''
    geos_geometry = GEOSGeometry(geometry)
    bbox_ch = GEOSGeometry("POLYGON ((3 44,3 50,14 50,14 44,3 44))")
    if geos_geometry.empty:
        message = "The geometry is empty: %(error)s"
        params = {'error': geos_geometry.wkt}
        logger.error(message, params)
        raise ValidationError(_(message), params=params, code='invalid')
    if not geos_geometry.valid:
        message = "The geometry is not valid: %(error)s"
        params = {'error': geos_geometry.valid_reason}
        logger.error(message, params)
        raise ValidationError(_(message), params=params, code='invalid')
    if not geos_geometry.srid:
        message = "No projection provided: SRID=%(error)s"
        params = {'error': geos_geometry.srid}
        logger.error(message, params)
        raise ValidationError(_(message), params=params, code='invalid')

    # transform geometry from textfield input if necessary
    if apply_transform and geos_geometry.srid != 4326:
        geos_geometry.transform(4326)
    elif geos_geometry.srid != 4326:
        message = 'Non permitted Projection. Projection must be wgs84 (SRID=4326) instead of ' \
            'SRID=%(error)s'
        params = {'error': geos_geometry.srid}
        logger.error(message, params)
        raise ValidationError(_(message), params=params, code='invalid')

    extent = geos_geometry.extent
    if abs(extent[1]) > 90 or abs(extent[-1]) > 90:
        message = "Latitude exceeds permitted value: %(error)s"
        params = {'error': (extent[1], extent[-1])}
        logger.error(message, params)
        raise ValidationError(_(message), params=params, code='invalid')
    if abs(extent[0]) > 180 or abs(extent[-2]) > 180:
        message = "Longitude exceeds usual value range: %(warning)s"
        params = {'warning': (extent[0], extent[-2])}
        logger.warning(message, params)

    if not geos_geometry.within(bbox_ch):
        message = "Location of asset is (partially) outside of Switzerland"
        params = {'warning': geos_geometry.wkt}
        logger.warning(message, params)
    return geometry


def validate_datetime_format(date_string):
    try:
        if date_string is not None and not isinstance(date_string, datetime):
            return fromisoformat(date_string)
        return date_string
    except ValueError as error:
        logger.error("Invalid datetime string %s", error)
        raise ValidationError(
            _('Invalid datetime string %(error)s'), params={'error': error}, code='invalid'
        ) from error


def validate_iso_8601_duration(duration: str) -> None:
    '''Raises a ValidationError if the given duration does not match the ISO 8601 format ("P3Y6M4DT12H30M5S")
    '''
    # Adapted from django.utils.dateparse.parse_duration to also cover
    #    - years (Y)
    #    - months (M)
    #    - weeks (W)
    iso8601_duration_re = _lazy_re_compile(
        r"^(?P<sign>[-+]?)"
        r"P"
        r"(?:(?P<years>\d+([.,]\d+)?)Y)?"
        r"(?:(?P<months>\d+([.,]\d+)?)M)?"
        r"(?:(?P<weeks>\d+([.,]\d+)?)W)?"
        r"(?:(?P<days>\d+([.,]\d+)?)D)?"
        r"(?:T"
        r"(?:(?P<hours>\d+([.,]\d+)?)H)?"
        r"(?:(?P<minutes>\d+([.,]\d+)?)M)?"
        r"(?:(?P<seconds>\d+([.,]\d+)?)S)?"
        r")?"
        r"$"
    )
    matches = iso8601_duration_re.match(duration)
    if not matches:
        raise ValidationError(
            _(f'Duration "{duration}" does not match ISO 8601 format.'), code='invalid'
        )


def validate_item_properties_datetimes(
    properties_datetime, properties_start_datetime, properties_end_datetime, properties_expires
):
    '''
    Validate the dependencies between the item datetime properties.
    This makes sure that either only the properties.datetime is set or
    both properties.start_datetime and properties.end_datetime are set.
    If properties.expires is set, the value must be greater than
    the properties.datetime or the properties.end_datetime.
    Raises:
        django.core.exceptions.ValidationError
    '''
    properties_datetime = validate_datetime_format(properties_datetime)
    properties_start_datetime = validate_datetime_format(properties_start_datetime)
    properties_end_datetime = validate_datetime_format(properties_end_datetime)
    properties_expires = validate_datetime_format(properties_expires)

    if properties_datetime is not None:
        if (properties_start_datetime is not None or properties_end_datetime is not None):
            message = 'Cannot provide together property datetime with datetime range ' \
                '(start_datetime, end_datetime)'
            logger.error(message)
            raise ValidationError(_(message), code='invalid')
        if properties_expires is not None:
            if properties_expires < properties_datetime:
                message = "Property expires can't refer to a date earlier than property datetime"
                raise ValidationError(_(message), code='invalid')

    if properties_datetime is None:
        if properties_end_datetime is None:
            message = "Property end_datetime can't be null when no property datetime is given"
            logger.error(message)
            raise ValidationError(_(message), code='invalid')
        if properties_start_datetime is None:
            message = "Property start_datetime can't be null when no property datetime is given"
            logger.error(message)
            raise ValidationError(_(message), code='invalid')
        if properties_end_datetime < properties_start_datetime:
            message = "Property end_datetime can't refer to a date earlier than property "\
            "start_datetime"
            raise ValidationError(_(message), code='invalid')
        if properties_expires is not None:
            if properties_expires < properties_end_datetime:
                message = "Property expires can't refer to a date earlier than property "\
                "end_datetime"
                raise ValidationError(_(message), code='invalid')


def validate_checksum_multihash_sha256(value):
    '''Validate the checksum multihash field

    The field value must be a multihash sha256 string

    Args:
        value: string
            multihash value

    Raises:
        ValidationError in case of invalid multihash value
    '''
    try:
        mhash = multihash.decode(multihash.from_hex_string(value))
    except (ValueError, TypeError) as error:
        logger.error("Invalid multihash %s; %s", value, error)
        raise ValidationError(_('Invalid multihash value; %(error)s'),
                              params={'error': error}, code='invalid') from None
    if mhash.code != HASH_CODES['sha2-256']:
        logger.error("Invalid multihash value: must be sha2-256 but is %s", CODE_HASHES[mhash.code])
        raise ValidationError(_('Invalid multihash value: must be sha2-256 but is %(code)s'),
                              params={'code': CODE_HASHES[mhash.code]}, code='invalid')


def validate_md5_parts(md5_parts, number_parts):
    '''Validate the md5_parts field.
    '''

    if not isinstance(md5_parts, list):
        logger.error(
            "Invalid md5_parts field %s, must be a list and is %s", md5_parts, type(md5_parts)
        )
        raise ValidationError(_('Invalid md5_parts field: must be a list but is %(type)s'),
                              params={'type': type(md5_parts)}, code='invalid')
    # sort and remove duplicate part number
    sorted_md5_parts = sorted(
        dict((item.get('part_number', 0) if isinstance(item, dict) else 0, item)
             for item in md5_parts).values(),
        key=lambda item: item.get('part_number', 0) if isinstance(item, dict) else 0
    )
    if len(sorted_md5_parts) != number_parts:
        logger.error(
            "Invalid md5_parts field value=%s: "
            "list has too few, too many or duplicate part_number item(s), "
            "it should have a total of %d non duplicated item(s)",
            md5_parts,
            number_parts
        )
        raise ValidationError(
            _('Missing, too many or duplicate part_number in md5_parts field list: '
              'list should have %(size)d item(s).'),
            params={'size': number_parts},
            code='invalid'
        )
    for i, item in enumerate(md5_parts):
        if not isinstance(item, dict):
            logger.error(
                "Invalid md5_parts[%d] field value=%s, must be a dict and is %s",
                i,
                item,
                type(item)
            )
            raise ValidationError(_('Invalid md5_parts[%(i)d] value: must be dict but is %(type)s'),
                                  params={'i': i, 'type': type(item)}, code='invalid')
        if 'part_number' not in item:
            logger.error(
                "Invalid md5_parts[%d] field value=%s, part_number field missing",
                i,
                item,
            )
            raise ValidationError(_('Invalid md5_parts[%(i)d] value: part_number field missing'),
                                  params={'i': i}, code='invalid')
        if (
            not isinstance(item['part_number'], int) or
            (item['part_number'] < 1 or item['part_number'] > number_parts)
        ):
            logger.error(
                "Invalid md5_parts[%d].part_number field value=%s: "
                "part_number field must be an int between 1 and %d",
                i,
                item['part_number'],
                number_parts
            )
            raise ValidationError(
                _('Invalid md5_parts[%(i)d].part_number value: '
                  'part_number field must be an int between 1 and %(number_parts)d'),
                params={'i': i, 'number_parts': number_parts}, code='invalid'
            )
        if 'md5' not in item:
            logger.error(
                "Invalid md5_parts[%d] field value=%s, md5 field missing",
                i,
                item,
            )
            raise ValidationError(_('Invalid md5_parts[%(i)d] value: md5 field missing'),
                                  params={'i': i}, code='invalid')
        if not isinstance(item['md5'], str) or item['md5'] == '' or not is_valid_b64(item['md5']):
            logger.error(
                "Invalid md5_parts[%d].md5 field value=%s: "
                "md5 field must be a non empty b64 encoded string; type=%s valid_b64=%s",
                i,
                item['md5'],
                type(item['md5']),
                is_valid_b64(item['md5'])
            )
            raise ValidationError(
                _('Invalid md5_parts[%(i)d].md5 value: '
                  'md5 field must be a non empty b64 encoded string'),
                params={'i': i - 1}, code='invalid'
            )


def validate_content_encoding(value):
    '''Validate the content_encoding field

    Args:
        value: str
            value to validate

     Raises:
        ValidationError in case of invalid content_encoding value
    '''
    # To start we are restrictive and only support the most common encoding, but if needed in
    # future we can enhanced it to other encoding (deflate and/or compress)
    supported_encodings = ['br', 'gzip']
    if value not in supported_encodings:
        raise ValidationError(
            _('Invalid encoding "%(encoding)s": must be one of "%(supported_encodings)s"'),
            params={'encoding': value, 'supported_encodings': ', '.join(supported_encodings)},
            code='invalid'
        )


def _validate_href_scheme(url, collection):
    """Validate if the url scheme is disallowed"""
    _url = urlparse(url)
    if _url.scheme in settings.DISALLOWED_EXTERNAL_ASSET_URL_SCHEMES:
        logger.warning(
            "Attempted external asset upload with disallowed URL scheme",
            extra={
                'url': url,
                'collection': collection,  # to have the means to know who this might have been
                'disallowed_schemes': settings.DISALLOWED_EXTERNAL_ASSET_URL_SCHEMES
            }
        )
        raise ValidationError(_(f'{_url.scheme} is not a allowed url scheme'))


def _validate_href_general_pattern(url, collection):
    try:
        validator = URLValidator()
        validator(url)
    except exceptions.ValidationError as exc:
        logger.warning(
            "Attempted external asset upload with invalid URL %s",
            url,
            extra={
                # to have the means to know who this might have been
                'collection': collection,
            }
        )

        error = _('Invalid URL provided')
        raise ValidationError(error) from exc


def _validate_href_configured_pattern(url, collection):
    """Validate the URL against the whitelist"""
    whitelist = collection.external_asset_whitelist

    for entry in whitelist:
        if url.startswith(entry):
            return True

    logger.warning(
        "Attempted external asset upload didn't match the whitelist",
        extra={
            # log collection to have the means to know who this might have been
            'url': url,
            'whitelist': whitelist,
            'collection': collection
        }
    )

    # none of the prefixes matches
    error = _("Invalid URL provided. It doesn't match the collection whitelist")
    raise ValidationError(error)


def _validate_href_reachability(url, collection):
    unreachable_error = _('Provided URL is unreachable')
    try:
        response = requests.head(url, timeout=settings.EXTERNAL_URL_REACHABLE_TIMEOUT)

        if response.status_code > 400:
            logger.warning(
                "Attempted external asset upload failed the reachability check",
                extra={
                    'url': url,
                    'collection': collection,  # to have the means to know who this might have been
                    'response': response,
                }
            )
            raise ValidationError(unreachable_error)
    except requests.Timeout as exc:
        logger.warning(
            "Attempted external asset upload resulted in a timeout",
            extra={
                'url': url,
                'collection': collection,  # to have the means to know who this might have been
                'exception': exc,
                'timeout': settings.EXTERNAL_URL_REACHABLE_TIMEOUT
            }
        )
        error = _('Checking href URL resulted in timeout')
        raise ValidationError(error) from exc
    except requests.ConnectionError as exc:
        logger.warning(
            "Attempted external asset upload resulted in connection error",
            extra={
                'url': url,
                'collection': collection,  # to have the means to know who this might have been
                'exception': exc,
            }
        )
        raise ValidationError(unreachable_error) from exc


def validate_href_url(url, collection):
    """Validate the href URL """

    _validate_href_scheme(url, collection)
    _validate_href_general_pattern(url, collection)
    _validate_href_configured_pattern(url, collection)
    _validate_href_reachability(url, collection)
