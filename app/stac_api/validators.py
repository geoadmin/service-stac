import logging
import re
from datetime import datetime

import multihash

from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from stac_api.utils import fromisoformat

logger = logging.getLogger(__name__)

MEDIA_TYPES = [
    ('application/x.ascii-grid+zip', 'Zipped ESRI ASCII raster format (.asc)', ['.zip']),
    ('application/x.ascii-xyz+zip', 'Zipped XYZ (.xyz)', ['.zip']),
    ('application/x.e00+zip', 'Zipped e00', ['.zip']),
    ('image/tiff; application=geotiff', 'GeoTIFF', ['.tiff', '.tif']),
    ('application/x.geotiff+zip', 'Zipped GeoTIFF', ['.zip']),
    ('application/x.tiff+zip', 'Zipped TIFF', ['.zip']),
    ('application/x.png+zip', 'Zipped PNG', ['.zip']),
    ('application/x.jpeg+zip', 'Zipped JPEG', ['.zip']),
    ('application/vnd.google-earth.kml+xml', 'KML', ['.kml']),
    ('application/vnd.google-earth.kmz', 'Zipped KML', ['.kmz']),
    ('application/x.dxf+zip', 'Zipped DXF', ['.zip']),
    ('application/gml+xml', 'GML', ['.gml', '.xml']),
    ('application/x.gml+zip', 'Zipped GML', ['.zip']),
    ('application/vnd.las', 'LIDAR', ['.las']),
    ('application/vnd.laszip', 'Zipped LIDAR', ['.laz', '.zip']),
    ('application/x.shapefile+zip', 'Zipped Shapefile', ['.zip']),
    ('application/x.filegdb+zip', 'Zipped File Geodatabase', ['.zip']),
    ('application/x.ms-access+zip', 'Zipped Personal Geodatabase', ['.zip']),
    ('application/x.ms-excel+zip', 'Zipped Excel', ['.zip']),
    ('application/x.tab+zip', 'Zipped Mapinfo-TAB', ['.zip']),
    ('application/x.tab-raster+zip', 'Zipped Mapinfo-Raster-TAB', ['.zip']),
    ('application/x.csv+zip', 'Zipped CSV', ['.zip']),
    ('text/csv', 'CSV', ['.csv']),
    ('application/geopackage+sqlite3', 'Geopackage', ['.gpkg']),
    ('application/x.geopackage+zip', 'Zipped Geopackage', ['.zip']),
    ('application/geo+json', 'GeoJSON', ['.json', '.geojson']),
    ('application/x.geojson+zip', 'Zipped GeoJSON', ['.zip']),
    ('application/x.interlis; version=2.3', 'Interlis 2', ['.xtf', '.xml']),
    ('application/x.interlis+zip; version=2.3', 'Zipped XTF (2.3)', ['.zip']),
    ('application/x.interlis; version=1', 'Interlis 1', ['.itf']),
    ('application/x.interlis+zip; version=1', 'Zipped ITF', ['.zip']),
    (
        'image/tiff; application=geotiff; profile=cloud-optimized',
        'Cloud Optimized GeoTIFF (COG)', ['.tiff', '.tif']
    ),
    ('application/pdf', 'PDF', ['.pdf']),
    ('application/x.pdf+zip', 'Zipped PDF', ['.zip']),
    ('application/json', 'JSON', ['.json']),
    ('application/x.json+zip', 'Zipped JSON', ['.zip']),
    ('application/x-netcdf', 'NetCDF', ['.nc']),
    ('application/x.netcdf+zip', 'Zipped NetCDF', ['.zip']),
    ('application/xml', 'XML', ['.xml']),
    ('application/x.xml+zip', 'Zipped XML', ['.zip']),
    ('application/vnd.mapbox-vector-tile', 'mbtiles', ['.mvt']),
    ('text/plain', 'Text', ['.txt']),
    ('text/x.plain+zip', 'Zipped text', ['.zip']),
]
MEDIA_TYPES_MIMES = [x[0] for x in MEDIA_TYPES]
MEDIA_TYPES_EXTENSIONS = [ext for media_type in MEDIA_TYPES for ext in media_type[2]]
MEDIA_TYPES_BY_TYPE = {media[0]: media for media in MEDIA_TYPES}


def validate_name(name):
    '''Validate name used in URL
    '''
    if not re.match(r'^[0-9a-z-_.]+$', name):
        logger.error('Invalid name %s, only the following characters are allowed: 0-9a-z-_.', name)
        raise ValidationError(
            _('Invalid id, only the following characters are allowed: 0-9a-z-_.'),
            code='id'
        )


def validate_asset_name(name):
    '''Validate Asset name used in URL
    '''
    if not name:
        logger.error('Invalid asset name, must not be empty')
        raise ValidationError({'id': _("Invalid id must not be empty")}, code='id')
    validate_name(name)
    ext = name.rsplit('.', maxsplit=1)[-1]
    if f'.{ext}' not in MEDIA_TYPES_EXTENSIONS:
        logger.error(
            'Invalid name %s extension %s, name must ends with a valid file extension', name, ext
        )
        raise ValidationError(
            _(f"Invalid id extension '.{ext}', id must have a valid file extension"),
            code='id'
        )


def validate_asset_name_with_media_type(name, media_type):
    '''Validate Asset name against the media type
    '''
    ext = f".{name.rsplit('.', maxsplit=1)[-1]}"
    if media_type not in MEDIA_TYPES_BY_TYPE:
        logger.error("Invalid media_type %s for asset %s", media_type, name)
        raise ValidationError(_(f"Invalid media type {media_type}"), code='type')
    if ext not in MEDIA_TYPES_BY_TYPE[media_type][2]:
        logger.error(
            "Invalid name %s extension %s, don't match the media type %s",
            name,
            ext,
            MEDIA_TYPES_BY_TYPE[media_type],
        )
        raise ValidationError(
            _(f"Invalid id extension '{ext}', id must match its media type {media_type}"),
            code='id'
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
            _(f'Invalid geoadmin:variant "{variant}", '
              'special characters beside one space are not allowed'),
            code="geoadmin:variant"
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
            _(f'Invalid rel attribute, must not be in {invalid_rel}'),
            code="rel"
        )


def validate_geometry(geometry):
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
    if geos_geometry.empty:
        message = "The geometry is empty: %s" % geos_geometry.wkt
        logger.error(message)
        raise ValidationError(_(message), code='geometry')
    if not geos_geometry.valid:
        message = "The geometry is not valid: %s" % geos_geometry.valid_reason
        logger.error(message)
        raise ValidationError(_(message), code='geometry')
    return geometry


def validate_item_properties_datetimes_dependencies(
    properties_datetime, properties_start_datetime, properties_end_datetime
):
    '''
    Validate the dependencies between the Item datetimes properties
    This makes sure that either only the properties.datetime is set or
    both properties.start_datetime and properties.end_datetime
    Raises:
        django.core.exceptions.ValidationError
    '''
    try:
        if not isinstance(properties_datetime, datetime) and properties_datetime is not None:
            properties_datetime = fromisoformat(properties_datetime)
        if (
            not isinstance(properties_start_datetime, datetime) and
            properties_start_datetime is not None
        ):
            properties_start_datetime = fromisoformat(properties_start_datetime)
        if (
            not isinstance(properties_end_datetime, datetime) and
            properties_end_datetime is not None
        ):
            properties_end_datetime = fromisoformat(properties_end_datetime)
    except ValueError as error:
        logger.error("Invalid datetime string %s", error)
        raise ValidationError(f'Invalid datetime string {error}') from error

    if properties_datetime is not None:
        if (properties_start_datetime is not None or properties_end_datetime is not None):
            message = 'Cannot provide together property datetime with datetime range ' \
                '(start_datetime, end_datetime)'
            logger.error(message)
            raise ValidationError(_(message))
    else:
        if properties_end_datetime is None:
            message = "Property end_datetime can't be null when no property datetime is given"
            logger.error(message)
            raise ValidationError(_(message))
        if properties_start_datetime is None:
            message = "Property start_datetime can't be null when no property datetime is given"
            logger.error(message)
            raise ValidationError(_(message))

    if properties_datetime is None:
        if properties_end_datetime < properties_start_datetime:
            message = "Property end_datetime can't refer to a date earlier than property "\
            "start_datetime"
            raise ValidationError(_(message))


def validate_item_properties_datetimes(
    properties_datetime, properties_start_datetime, properties_end_datetime
):
    '''
    Validate datetime values in the properties Item attributes
    '''
    validate_item_properties_datetimes_dependencies(
        properties_datetime,
        properties_start_datetime,
        properties_end_datetime,
    )


def validate_asset_multihash(value):
    '''Validate the Asset multihash field

    The field value must be a multihash string

    Args:
        value: string
            multihash value

    Raises:
        ValidationError in case of invalid multihash value
    '''
    try:
        mhash = multihash.decode(multihash.from_hex_string(value))
    except ValueError as error:
        logger.error("Invalid multihash %s; %s", value, error)
        raise ValidationError(
            code='checksum:multihash',
            message=_('Invalid multihash value; %(error)s'),
            params={'error': error}
        ) from None
