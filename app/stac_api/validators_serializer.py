import json
import logging
from decimal import Decimal

import botocore
import multihash
from multihash import from_hex_string
from multihash import to_hex_string

from django.conf import settings
from django.contrib.gis.gdal.error import GDALException
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.utils.translation import gettext_lazy as _

from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError

from stac_api.utils import create_multihash
from stac_api.utils import create_multihash_string
from stac_api.utils import fromisoformat
from stac_api.utils import get_asset_path
from stac_api.utils import get_s3_resource
from stac_api.utils import harmonize_post_get_for_search
from stac_api.validators import validate_geometry

logger = logging.getLogger(__name__)


def validate_json_payload(serializer):
    '''
    Validate JSON payload and raise error, if extra payload or read-only fields
    in payload are found
    Args:
        serializer: serializer for which payload is checked

    Raises:
        ValidationError if extra or read-only fields in payload are found
    '''

    expected_payload = list(serializer.fields.keys())
    expected_payload_read_only = [
        field for field in serializer.fields if serializer.fields[field].read_only
    ]

    errors = {}
    for key in serializer.initial_data.keys():
        if key not in expected_payload:
            logger.error('Found unexpected payload %s', key)
            errors[key] = _("Unexpected property in payload")
        if key in expected_payload_read_only:
            logger.error('Found read-only payload %s', key)
            errors[key] = _("Found read-only property in payload")

    if errors:
        raise ValidationError(code='payload', detail=errors)


def validate_asset_href_path(item, asset_name, path):
    '''Validate Asset href path

    The href path must follow the convention: [PREFIX/]COLLECTION_NAME/ITEM_NAME/ASSET_NAME
    where PREFIX is parsed from settings.AWS_S3_CUSTOM_DOMAIN if available

    Args:
        item: Item
            Item object's in which the Assets is located
        asset_name: string
            Asset's name
        path: string
            Href path to validate

    Raises:
        ValidationError in case of invalid path
    '''
    expected_path = get_asset_path(item, asset_name)
    if settings.AWS_S3_CUSTOM_DOMAIN:
        prefix_path = settings.AWS_S3_CUSTOM_DOMAIN.strip('/').split('/', maxsplit=1)[1:]
        expected_path = '/'.join(prefix_path + [expected_path])
    if path != expected_path:
        logger.error("Invalid path %s; don't follow the convention %s", path, expected_path)
        raise ValidationError({
            'href': _(f"Invalid path; should be {expected_path} but got {path}")
        })


def validate_asset_file(href, original_name, attrs):
    '''Validate Asset file

    Validate the Asset file located at href. The file must exist and match the multihash. The file
    hash is retrieved by doing a HTTP HEAD request at href.

    Args:
        href: string
            Asset file href to validate
        original_name: string
            Asset original name in case of renaming
        expected_multihash: string (optional)
            Asset file expected multihash (must be a sha2-256 multihash !)

    Raises:
        rest_framework.exceptions.ValidationError:
            in case of invalid Asset (asset doesn't exist or hash doesn't match)
        rest_framework.exceptions.APIException:
            in case of other networking errors
    '''
    logger.debug('Validate asset file at %s with attrs %s', href, attrs)

    asset_path = get_asset_path(attrs['item'], original_name)
    try:
        s3 = get_s3_resource()
        obj = s3.Object(settings.AWS_STORAGE_BUCKET_NAME, asset_path)
        obj.load()
        logger.debug('S3 obj %s etag=%s, metadata=%s', asset_path, obj.e_tag, obj.metadata)
    except botocore.exceptions.ClientError as error:
        logger.error('Failed to retrieve S3 object %s metadata: %s', asset_path, error)
        if error.response.get('Error', {}).get('Code', None) == '404':
            logger.error('Asset at href %s doesn\'t exists', href)
            raise ValidationError({'href': _(f"Asset doesn't exists at href {href}")}) from error
        raise APIException({'href': _("Error while checking href existence")}) from error

    # Get the hash from response
    asset_multihash = None
    asset_sha256 = obj.metadata.get('sha256', None)
    asset_md5 = obj.e_tag.strip('"')
    logger.debug(
        'Asset file %s checksums from headers: sha256=%s, md5=%s', href, asset_sha256, asset_md5
    )
    if asset_sha256:
        asset_multihash = create_multihash(asset_sha256, 'sha2-256')
    elif asset_md5:
        asset_multihash = create_multihash(asset_md5, 'md5')

    if asset_multihash is None:
        logger.error(
            'Asset at href %s, doesn\'t provide a sha2-256 hash in header x-amz-meta-sha256 ' \
            'or an ETag md5 checksum', href
        )
        raise APIException({
            'href': _(f"Asset at href {href} doesn't provide a valid checksum header "
                      "(ETag or x-amz-meta-sha256) for validation")
        })

    expected_multihash = attrs.get('checksum_multihash', None)
    if expected_multihash is None:
        # checksum_multihash attribute not found in attributes, therefore set it with the multihash
        # created from the HEAD Header and terminates the validation
        attrs['checksum_multihash'] = create_multihash_string(
            asset_multihash.digest, asset_multihash.code
        )
        return attrs

    # When a checksum_multihash is found in attributes then make sure that it match the checksum of
    # found in the HEAD header.

    _validate_asset_file_checksum(href, expected_multihash, asset_multihash)

    return attrs


def _validate_asset_file_checksum(href, expected_multihash, asset_multihash):
    expected_multihash = multihash.decode(from_hex_string(expected_multihash))

    logger.debug(
        'Validate asset file checksum at %s with multihash %s/%s (from headers), expected %s/%s '
        '(from checksum:multishash attribute)',
        href,
        to_hex_string(asset_multihash.digest),
        asset_multihash.name,
        to_hex_string(expected_multihash.digest),
        expected_multihash.name
    )

    if asset_multihash.name != expected_multihash.name:
        logger.error(
            'Asset at href %s, with multihash name=%s digest=%s, doesn\'t match the expected '
            'multihash name=%s digest=%s defined in checksum:multihash attribute',
            href,
            asset_multihash.name,
            to_hex_string(asset_multihash.digest),
            expected_multihash.name,
            to_hex_string(expected_multihash.digest)
        )
        raise ValidationError(
            code='href',
            detail=_(f"Asset at href {href} has a {asset_multihash.name} multihash while a "
                     f"{expected_multihash.name} multihash is defined in the checksum:multihash "
                     "attribute")
        )

    if asset_multihash != expected_multihash:
        logger.error(
            'Asset at href %s, with multihash name=%s digest=%s, doesn\'t match the '
            'checksum:multihash value name=%s digest=%s',
            href,
            asset_multihash.name,
            to_hex_string(asset_multihash.digest),
            expected_multihash.name,
            to_hex_string(expected_multihash.digest)
        )
        raise ValidationError(
            code='href',
            detail=_(f"Asset at href {href} with {asset_multihash.name} hash "
                     f"{to_hex_string(asset_multihash.digest)} doesn't match the "
                     f"checksum:multihash {to_hex_string(expected_multihash.digest)}")
        )


class ValidateSearchRequest:
    '''Validates the query parameter for the search endpoint.

    The main function is validate. If everything in the query parameter is ok
    this class does nothing.

    If there are errors in the validation it sums them up and returns the summary
    when raising a ValidationError.
    '''

    def __init__(self):
        self.errors = {}  # a list with all the validation errors
        self.max_len_array = 2000
        self.max_times_same_query_attribute = 20
        self.max_query_attributes = 50

        # Note: if these values are adapted, don't forget to
        # update the spec accordingly.
        self.queriable_date_fields = ['created', 'updated']
        self.queriable_str_fields = ['title']

    def validate(self, request):
        '''Validates the request of the search endpoint

        This function validates the request of the search endpoint. As a simplification the
        requests of GET and POST are harmonized. Then the search params are validated. This
        function gathers as much validation information as possible. If there is one error
        or several, finally it raises one error with a complete validation feedback.

        Args:
            request (RequestDict)
                The Request (POST or GET)

        Raises:
            ValidationError(code, details)
        '''
        # harmonize GET and POST
        query_param = harmonize_post_get_for_search(request)

        if request.method == "POST":
            self.validate_query_parameters_post_search(query_param)

        if 'bbox' in query_param:
            self.validate_bbox(query_param['bbox'])
        if 'datetime' in query_param:
            self.validate_date_time(query_param['datetime'])
        if 'ids' in query_param:
            self.validate_array_of_strings(query_param['ids'], 'ids')
        if 'collections' in query_param:
            self.validate_array_of_strings(query_param['collections'], 'collections')
        if 'query' in query_param:
            self.validate_query(query_param['query'])
        if 'intersects' in query_param:  # only in POST
            self.validate_intersects(json.dumps(query_param['intersects']))

        # Raise ERROR with a list of parsed errors
        if self.errors:
            for key in self.errors:
                logger.error('%s: %s', key, self.errors[key])
            raise ValidationError(code='query-invalid', detail=self.errors)

    def validate_query(self, query):
        '''Validates the query parameter

        The query parameter is being validated. If an validation error is detected,
        an information is being added to the dict self.errors

        Args:
            query: string
                The query parameter to be validated.
        '''
        # summing up the fields based of different types
        queriable_fields = self.queriable_date_fields + self.queriable_str_fields

        # validate json
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError as error:
            message = f"The application could not decode the query parameter" \
                      f"Please check the syntax ({error})." \
                      f"{query}"
            raise ValidationError(code='query-invalid', detail=_(message))

        self._query_validate_length_of_query(query_dict)
        for attribute in query_dict:
            if not attribute in queriable_fields:
                message = f"Invalid field in query argument. The field {attribute} is not " \
                          f"a propertie. Use one of these {queriable_fields}"
                self.errors[f"query-attributes-{attribute}"] = _(message)

            # validate operators
            self._query_validate_operators(query_dict, attribute)

    def _query_validate_length_of_query(self, query_dict):
        '''Test the maximal number of attributes in the query parameter
        Args:
            query_dict: dictionary
                To test how many query attributes are provided
        Raise:
            ValidationError
        '''
        if len(query_dict) > self.max_query_attributes:
            message = f"Too many attributes in query parameter. Max. " \
                      f"{self.max_query_attributes} allowed"
            logger.error(message)
            raise ValidationError(code='query-invalid', detail=_(message))

    def _query_validate_operators(self, query_dict, attribute):
        '''
        Checks if the query param is build out of valid operators (like eq, lt).

        There is a distinction between the allowed operators between string operators
        and number operators.

        Args:
            query_dict: dict
                A dictionary of request payload
            attribute: string
                The attribute that is filtered by the operator
        '''
        int_operators = ["eq", "neq", "lt", "lte", "gt", "gte"]
        str_operators = ["startsWith", "endsWith", "contains", "in"]
        operators = int_operators + str_operators

        # iterate trough the operators
        for operator in query_dict[attribute]:
            if operator in operators:
                # get the values which shall be filtered with the operator
                value = query_dict[attribute][operator]
                # validate type to operation
                if (
                    isinstance(value, str) and operator in int_operators and
                    attribute in int_operators
                ):
                    message = f"You are not allowed to compare a string/date ({attribute})"\
                              f" with a number operator." \
                              f"for string use one of these {str_operators}"
                    self.errors[f"query-operator-{operator}"] = _(message)
                if (isinstance(value, int) and operator in str_operators):
                    message = f"You are not allowed to compare a number or a date with" \
                              f"a string operator." \
                              f"For numbers use one of these {int_operators}"
                    self.errors[f"query-operator-{operator}"] = _(message)
                self._query_validate_in_operator(attribute, value)
            else:
                message = f"Invalid operator in query argument. The operator {operator} " \
                          f"is not supported. Use: {operators}"
                self.errors[f"query-operator-{operator}"] = _(message)

    def _query_validate_in_operator(self, attribute, value):
        '''
        Tests if the type in the list stays the same.
        This is a helper function of _query_validate_operators.
        If there is an error, a corresponding entry will be added to the self.errors dict

        Args:
            attribute: string
                The attribute to be tested
            value: string or list[strings]
                The value to be tested (string or datetime)
        '''
        # validate date
        if attribute in self.queriable_date_fields:
            try:
                if isinstance(value, list):
                    self.validate_list_length(value, 'query')
                    value = [fromisoformat(i) for i in value]
                else:
                    value = fromisoformat(value)
            except ValueError as error:
                message = f"{value} is an invalid dateformat: ({error})"
                self.errors[f"query-attributes-{attribute}"] = _(message)

        # validate str
        if attribute in self.queriable_str_fields:
            message = ''
            if isinstance(value, list):
                self.validate_list_length(value, 'query')
                for val in value:
                    if not isinstance(val, str):
                        message = f"{message} The values have to be strings." \
                                  f" The value {val} is not a string"
            else:
                if not isinstance(value, str):
                    message = f"{message} The values have to be strings." \
                              f" The value {value} is not a string"
            if message != '':
                self.errors[f"query-attributes-{attribute}"] = _(message)

    def validate_date_time(self, date_time):
        '''
        Validate the datetime query as specified in the api-spec.md.
        If there is an error, a corresponding entry will be added to the self.errors dict

        Args:
            date_time: string
                The datetime to get validated
        '''
        start, sep, end = date_time.partition('/')
        message = None
        try:
            if start != '..':
                start = fromisoformat(start)
            if end and end != '..':
                end = fromisoformat(end)
        except ValueError as error:
            message = "Invalid datetime query parameter, must be isoformat. "
            self.errors['datetime'] = _(message)

        if end == '':
            end = None

        if start == '..' and (end is None or end == '..'):
            message = f"{message} Invalid datetime query parameter, " \
                f"cannot start with open range when no end range is defined"

        if message:
            self.errors['datetime'] = _(message)

    def validate_array_of_strings(self, array_of_strings, key):
        '''
        Validation of the ids. The ids have to be an array of strings. If this is not the
        case, an entry will be added to the self.errors dict.

        Args:
            ids: list[strings]
                Should be an array of stings. But it is about testing, if this is the case.
            key: string
                The key that has to be added to the error dict.
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
            list_to_validate: list
                A list, which length will be validated
            key: string
                The key that has to be added to the error dict
        '''
        if len(list_to_validate) > self.max_len_array:
            message = f"The length of the list in the query is too long." \
                      f"The list {list_to_validate} should not be longer than {self.max_len_array}."
            self.errors[f"{key}-length"] = _(message)

    def validate_bbox(self, bbox):
        '''
        Validation of the bbox. If the creation of a
        geometry (point or polygon) would not work, the function adds
        a entry to the self.errors dict.

        Args:
            bbox: string
                The bbox is a string that has to be composed of 4 comma-seperated
                float values. F. ex.: 5.96,45.82,10.49,47.81
        '''
        try:
            list_bbox_values = bbox.split(',')
            if (
                Decimal(list_bbox_values[0]) == Decimal(list_bbox_values[2]) and
                Decimal(list_bbox_values[1]) == Decimal(list_bbox_values[3])
            ):
                bbox_geometry = Point(float(list_bbox_values[0]), float(list_bbox_values[1]))
            else:
                bbox_geometry = Polygon.from_bbox(list_bbox_values)
            validate_geometry(bbox_geometry)

        except (ValueError, ValidationError, IndexError, GDALException) as error:
            message = f"Invalid bbox query parameter: " \
                      f"f.ex. bbox=5.96,45.82,10.49,47.81, {bbox} ({error})"
            self.errors['bbox'] = _(message)

    def validate_intersects(self, geojson):
        '''Validates the geojson in the intersects parameter.

        To test, if the string is valid, a geometry is being build out of it. If it is not
        possible, the dict self.errors is being widened with the corresponding information.

        Args:
            geojson: string
                The geojson string to be validated
        '''
        try:
            intersects_geometry = GEOSGeometry(geojson)
            validate_geometry(intersects_geometry)
        except (ValueError, ValidationError, GDALException) as error:
            message = f"Invalid query: " \
                f"Could not transform {geojson} to a geometry; {error}"
            self.errors['intersects'] = _(message)

    def validate_query_parameters_post_search(self, query_param):
        '''Validates the query parameters for POST requests on the search endpoint.
        If any invalid query parameters are found, the dict self.errors will be extended
        with the corresponding message.

        Args:
            query_param: dict
                Copy of the harmonized QueryDict
        '''
        accepted_query_parameters = [
            "bbox", "collections", "datetime", "ids", "intersects", "limit", "cursor", "query"
        ]
        wrong_query_parameters = set(query_param.keys()).difference(set(accepted_query_parameters))
        if wrong_query_parameters:
            self.errors.update(
                {
                    wrong_query_param:
                    _(
                        f"The query contains the following non-queriable parameter: " \
                            f" {wrong_query_param}."
                    )
                    for wrong_query_param in wrong_query_parameters
                }
            )
            logger.error(
                'Query contains the non-allowed parameter(s): %s', list(wrong_query_parameters)
            )
