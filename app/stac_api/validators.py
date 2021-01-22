import json
import logging
import re
from datetime import datetime

import multihash

from django.contrib.gis.gdal.error import GDALException
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from rest_framework.exceptions import ValidationError as RestValidationError

from stac_api.utils import fromisoformat
from stac_api.utils import harmonize_post_get_for_search

logger = logging.getLogger(__name__)

MEDIA_TYPES = [
    ('application/x.ascii-grid+zip', 'Zipped ESRI ASCII raster format (.asc)', '.zip'),
    ('application/x.ascii-xyz+zip', 'Zipped XYZ (.xyz)', '.zip'),
    ('application/x.e00+zip', 'Zipped e00', '.zip'),
    ('image/tiff; application=geotiff', 'GeoTIFF', '.tiff or .tif'),
    ('application/x.geotiff+zip', 'Zipped GeoTIFF', '.zip'),
    ('application/x.tiff+zip', 'Zipped TIFF', '.zip'),
    ('application/x.png+zip', 'Zipped PNG', '.zip'),
    ('application/x.jpeg+zip', 'Zipped JPEG', '.zip'),
    ('application/vnd.google-earth.kml+xml', 'KML', '.kml'),
    ('application/vnd.google-earth.kmz', 'Zipped KML', '.kmz'),
    ('application/x.dxf+zip', 'Zipped DXF', '.zip'),
    ('application/gml+xml', 'GML', '.gml or .xml'),
    ('application/x.gml+zip', 'Zipped GML', '.zip'),
    ('application/vnd.las', 'LIDAR', '.las'),
    ('application/vnd.laszip', 'Zipped LIDAR', '.laz or .zip'),
    ('application/x.shapefile+zip', 'Zipped Shapefile', '.zip'),
    ('application/x.filegdb+zip', 'Zipped File Geodatabase', '.zip'),
    ('application/x.ms-access+zip', 'Zipped Personal Geodatabase', '.zip'),
    ('application/x.ms-excel+zip', 'Zipped Excel', '.zip'),
    ('application/x.tab+zip', 'Zipped Mapinfo-TAB', '.zip'),
    ('application/x.tab-raster+zip', 'Zipped Mapinfo-Raster-TAB', '.zip'),
    ('application/x.csv+zip', 'Zipped CSV', '.zip'),
    ('text/csv', 'CSV', '.csv'),
    ('application/geopackage+sqlite3', 'Geopackage', '.gpkg'),
    ('application/x.geopackage+zip', 'Zipped Geopackage', '.zip'),
    ('application/geo+json', 'GeoJSON', '.json or .geojson'),
    ('application/x.geojson+zip', 'Zipped GeoJSON', '.zip'),
    ('application/x.interlis; version=2.3', 'Interlis 2', '.xtf or .xml'),
    ('application/x.interlis+zip; version=2.3', 'Zipped XTF (2.3)', '.zip'),
    ('application/x.interlis; version=1', 'Interlis 1', '.itf'),
    ('application/x.interlis+zip; version=1', 'Zipped ITF', '.zip'),
    (
        'image/tiff; application=geotiff; profile=cloud-optimized',
        'Cloud Optimized GeoTIFF (COG)',
        '.tiff or .tif'
    ),
    ('application/pdf', 'PDF', '.pdf'),
    ('application/x.pdf+zip', 'Zipped PDF', '.zip'),
    ('application/json', 'JSON', '.json'),
    ('application/x.json+zip', 'Zipped JSON', '.zip'),
    ('application/x-netcdf', 'NetCDF', '.nc'),
    ('application/x.netcdf+zip', 'Zipped NetCDF', '.zip'),
    ('application/xml', 'XML', '.xml'),
    ('application/x.xml+zip', 'Zipped XML', '.zip'),
    ('application/vnd.mapbox-vector-tile', 'mbtiles', '???'),
    ('text/plain', 'Text', '.txt'),
    ('text/x.plain+zip', 'Zipped text', '.zip'),
]
MEDIA_TYPES_MIMES = [x[0] for x in iter(MEDIA_TYPES)]


def validate_name(name):
    '''Validate name used in URL
    '''
    if not re.match(r'^[0-9a-z-_.]+$', name):
        logger.error('Invalid name %s, only the following characters are allowed: 0-9a-z-_.', name)
        raise ValidationError(
            _('Invalid name, only the following characters are allowed: 0-9a-z-_.'),
            code='id'
        )


def validate_geoadmin_variant(variant):
    '''Validate geoadmin:variant, it should not have special characters'''
    if not re.match('^[a-zA-Z0-9]+$', variant):
        logger.error(
            "Invalid geoadmin:variant property %s, special characters not allowed", variant
        )
        raise ValidationError(
            _("Invalid geoadmin:variant, special characters not allowed"),
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
        )


class ValidateSearch:

    def __init__(self, request):
        self.errors = {}  # a list with all the validation errors
        self.max_len_array = 2000

        self.validate(request)

    def validate(self, request):
        # harmonize GET and POST
        query_param = harmonize_post_get_for_search(request)

        if 'bbox' in query_param:
            self.validate_bbox(query_param['bbox'])
        if 'datetime' in query_param:
            self.validate_date_time(query_param['datetime'])
        if 'ids' in query_param:
            self.validate_array_of_strings(query_param['ids'], 'ids')
        if 'collections' in query_param:
            self.validate_array_of_strings(query_param['collections'], 'collections')
        if 'query' in query_param:
            pass
            #self.validate_query(query_param['query'])
        if 'intersects' in query_param:  # only in POST
            self.validate_intersects(json.dumps(query_param['intersects']))

        if self.errors:
            logger.error(">>>>>>> %s ", self.errors)
            raise RestValidationError(code='query', detail=self.errors)

    def validate_query(self, query):  # pylint: disable=too-many-branches
        # DOTO
        queriable_date_fields = ['datetime', 'created', 'updated']
        queriable_str_fields = ['title']
        int_operators = ["eq", "neq", "lt", "lte", "gt", "gte"]
        str_operators = ["startsWith", "endsWith", "contains", "in"]
        operators = int_operators + str_operators
        queriable_fields = queriable_date_fields + queriable_str_fields

        for attribute in query:  # pylint: disable=too-many-nested-blocks

            # iterate trough the fields given in the query parameter
            if attribute in queriable_fields:
                logger.debug("attribute: %s", attribute)
                # iterate trough the operators
                for operator in query[attribute]:
                    if operator in operators:
                        value = query[attribute][operator]  # get the values given by the operator
                        # validate type to operation
                        if (
                            isinstance(value, str) and operator in int_operators and
                            attribute in int_operators
                        ):
                            message = f"You are not allowed to compare a string/date ({attribute})"\
                                      f" with a number operator." \
                                      f"for string use one of these {str_operators}"
                            logger.error(message)
                            raise ValidationError(_(message))
                        if (
                            isinstance(value, int) and operator in str_operators and
                            operator in str_operators
                        ):
                            message = f"You are not allowed to compare a number or a date with" \
                                      f"a string operator." \
                                      f"For numbers use one of these {int_operators}"
                            logger.error(message)
                            raise ValidationError(_(message))

                        # treat date
                        if attribute in queriable_date_fields:
                            try:
                                if isinstance(value, list):
                                    value = [fromisoformat(i) for i in value]
                                else:
                                    value = fromisoformat(value)
                            except ValueError as error:
                                message = f"Invalid dateformat: ({error})"
                                logger.error(message)
                                raise ValidationError(_(message))

                        logger.debug("query_filter: ")
                        logger.debug("operator: %s", operator)
                        logger.debug("value: %s", value)
                    else:
                        message = f"Invalid operator in query argument. The operator {operator} " \
                                  f"is not supported. Use: {operators}"
                        logger.error(message)
                        raise ValidationError(_(message))
            else:
                message = f"Invalid field in query argument. The field {attribute} is not " \
                          f"a propertie. Use one of these {queriable_fields}"
                logger.error(message)
                raise ValidationError(_(message))

    def validate_date_time(self, date_time):
        '''Validate the datetime query as specified in the api-spec.md.
        '''
        start, sep, end = date_time.partition('/')
        message = None
        try:
            if start != '..':
                start = datetime.fromisoformat(start.replace('Z', '+00:00'))
            if end and end != '..':
                end = datetime.fromisoformat(end.replace('Z', '+00:00'))
        except ValueError as error:
            message = "Invalid datetime query parameter, must be isoformat. "
            self.errors['date_time'] = _(message)

        if end == '':
            end = None

        if start == '..' and (end is None or end == '..'):
            message = f"{message} Invalid datetime query parameter, " \
                f"cannot start with open range when no end range is defined"

        if message:
            self.errors['date_time'] = _(message)

    def validate_array_of_strings(self, array_of_strings, key):
        '''
        Validation of the ids. The ids have to be an array of strings. If this is not the
        case, an entry will be added to the error dict.

        Args:
            ids: Should be an array of stings. But it is about testing, if this is the case.
        key (string): The key that has to be added to the error dict.
        '''
        if not isinstance(array_of_strings, list):
            message = f"The ids have to be within an array. " \
                      f"Please check the type of {array_of_strings}"
            self.errors[key] = _(message)
        else:
            for string_to_validate in array_of_strings:
                if not isinstance(string_to_validate, str):
                    message = f"Each entry in {key} has to be a string. " \
                      f"Please check the type of {key}: {string_to_validate}"
                    self.errors[key] = _(message)
        self.validate_list_length(array_of_strings, key)

    def validate_list_length(self, list_to_validate, key):
        '''
        Validate the length of a list. If the length exceeds the max, a error message is
        added to the error dict

        Args:
            list_to_validate (list): a list, which length will be validated
            key (string): The key that has to be added to the error dict
        '''
        if len(list_to_validate) > self.max_len_array:
            message = f"The length of the list in the query is too long." \
                      f"The list {list_to_validate} should not be longer than {self.max_len_array}."
            self.errors[key] = _(message)

    def validate_bbox(self, bbox):
        '''
        Validation of the bbox. If the creation of a
        geometry (point or polygon) would not work, the function adds
        a entry to the error dict.

        Args:
            bbox (string): The bbox is a string that has to be composed of 4 comma-seperated
                            float values. F. ex.: 5.96,45.82,10.49,47.81
        '''
        try:
            list_bbox_values = bbox.split(',')
            if (
                list_bbox_values[0] == list_bbox_values[2] and
                list_bbox_values[1] == list_bbox_values[3]
            ):
                bbox_geometry = Point(float(list_bbox_values[0]), float(list_bbox_values[1]))
            else:
                bbox_geometry = Polygon.from_bbox(list_bbox_values)
            validate_geometry(bbox_geometry)

        except (ValueError, ValidationError, IndexError) as error:
            message = f"Invalid bbox query parameter: " \
                      f"f.ex. bbox=5.96,45.82,10.49,47.81, {bbox} ({error})"
            self.errors['bbox'] = _(message)

    def validate_intersects(self, geojson):
        try:
            intersects_geometry = GEOSGeometry(geojson)
            validate_geometry(intersects_geometry)
        except (ValueError, ValidationError, GDALException) as error:
            message = f"Invalid query: " \
                f"Could not transform {geojson} to a geometry; {error}"
            self.errors['intersects'] = _(message)
