import hashlib
import json
import logging
import os
from base64 import b64decode
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from decimal import InvalidOperation
from enum import Enum
from io import StringIO
from typing import Any
from typing import TextIO
from urllib import parse

import boto3
import multihash
from botocore.client import Config

from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.core.management.base import CommandParser
from django.urls import reverse

from stac_api.exceptions import NotImplementedException

logger = logging.getLogger(__name__)

AVAILABLE_S3_BUCKETS = Enum('AVAILABLE_S3_BUCKETS', list(settings.AWS_SETTINGS.keys()))
API_VERSION = Enum('API_VERSION', ['v09', 'v1'])


def call_calculate_extent(*args, **kwargs):
    out = StringIO()
    call_command(
        "calculate_extent",
        *args,
        stdout=out,
        stderr=StringIO(),
        **kwargs,
    )
    return out.getvalue()


def isoformat(date_time):
    '''Return a datetime string in isoformat using 'Z' as timezone instead of '+00:00'
    '''
    return date_time.isoformat().replace('+00:00', 'Z')


def fromisoformat(date_time):
    '''Return a datetime object from a isoformated datetime string
    '''
    return datetime.fromisoformat(date_time.upper().replace('Z', '+00:00'))


def utc_aware(date_time):
    '''Return a UTC date_time aware object
    '''
    return date_time.replace(tzinfo=timezone.utc)


def get_link(links, rel, raise_exception=False):
    '''Get link from list based on his rel attribute

    Args:
	    links: list
			list of link object: {'href': url, 'rel': str}
        rel: string
            rel attribute to look for
        raise_exception: boolean (default=False)
            raises KeyError instead of returning None when link is not found

    Returns:
        The link object if found, else None
    '''
    for link in links:
        if link['rel'] == rel:
            return link
    if raise_exception:
        raise KeyError(f'Link with rel {rel} not found')
    return None


def get_provider(providers, name, raise_exception=False):
    '''Get provider from list based on his name attribute

    Args:
	    providers: list
			list of provider object
        name: string
            name attribute to look for
        raise_exception: boolean (default=False)
            raises KeyError instead of returning None when provider is not found

    Returns:
        The provider object if found, else None
    '''
    for provider in providers:
        if provider['name'] == name:
            return provider
    if raise_exception:
        raise KeyError(f'Provider with name {name} not found')
    return None


def get_asset_path(item, asset_name):
    '''Returns the asset path on S3.

    The path is defined as follow: COLLECTION_NAME/ITEM_NAME/ASSET_NAME

    Args:
        item: Item
            Item instance in which the asset is attached
        asset_name: string
            Asset's name

    Returns:
        Assets path on S3
    '''
    return '/'.join([item.collection.name, item.name, asset_name])


def get_collection_asset_path(collection, asset_name):
    '''Returns the asset path on S3.

    The path is defined as follow: COLLECTION_NAME/ASSET_NAME

    Args:
        collection: Collection
            Collection instance in which the asset is attached
        asset_name: string
            Asset's name

    Returns:
        Assets path on S3
    '''
    return '/'.join([collection.name, asset_name])


def _get_boto_access_kwargs(s3_bucket: AVAILABLE_S3_BUCKETS = AVAILABLE_S3_BUCKETS.legacy):
    """Build the arguments for client and resource calls to boto3

    Both boto3.resource and boto3.client need certain arguments to establish
    a connection. Depending on the bucket configuration used, we pass more or
    less arguments to those functions.
    """
    s3_config = settings.AWS_SETTINGS[s3_bucket.name]

    # basic access configuration
    client_access_kwargs = {
        "endpoint_url": s3_config['S3_ENDPOINT_URL'],
        "region_name": s3_config['S3_REGION_NAME'],
        "config": Config(signature_version=s3_config['S3_SIGNATURE_VERSION']),
    }

    # for the key access type, use the configured key/secret
    # otherwise let it use the environment (i.e. AWS_ROLE_ARN specifically)
    if s3_config['access_type'] == "key":
        client_access_kwargs.update({
            "aws_access_key_id": s3_config['ACCESS_KEY_ID'],
            "aws_secret_access_key": s3_config['SECRET_ACCESS_KEY']
        })

    # for the service account type, we need to make sure the environment contains
    # the variable AWS_ROLE_ARN for it to work
    # as it seems, we can't pass this explicitly
    # The variable is set by AWS itself
    if s3_config["access_type"] == "service_account":
        needed_env_vars = ['AWS_ROLE_ARN', 'AWS_WEB_IDENTITY_TOKEN_FILE']
        for env_var in needed_env_vars:
            if env_var not in os.environ:
                raise EnvironmentError(
                    f"For the {s3_bucket} bucket the environment variable "
                    "{env_var} must be configured"
                )

    return client_access_kwargs


def get_s3_resource(s3_bucket: AVAILABLE_S3_BUCKETS = AVAILABLE_S3_BUCKETS.legacy):
    '''Returns an AWS S3 resource

    Returns:
        AWS S3 resource
    '''

    return boto3.resource('s3', **(_get_boto_access_kwargs(s3_bucket)))


def get_s3_client(s3_bucket: AVAILABLE_S3_BUCKETS = AVAILABLE_S3_BUCKETS.legacy):
    '''Returns an AWS S3 client

    Returns:
        AWS S3 client
    '''
    client = boto3.client('s3', **(_get_boto_access_kwargs(s3_bucket)))

    return client


def build_asset_href(request, path):
    '''Build asset href

    Args:
        request: HttpRequest
            Request
        path: string
            Asset path

    Returns:
        Asset full href value
    '''
    if not path:
        return None

    # Assets file are served by an AWS S3 services. This service uses the same domain as
    # the API but could defer, especially for local development, so check first
    # AWS_LEGACY['S3_CUSTOM_DOMAIN']
    if settings.AWS_SETTINGS['legacy']['S3_CUSTOM_DOMAIN']:
        # By definition we should not mixed up HTTP Scheme (HTTP/HTTPS) within our service,
        # although the Assets file are not served by django we configure it with the same scheme
        # as django that's why it is kind of safe to use the django scheme.
        custom_domain = settings.AWS_SETTINGS['legacy']['S3_CUSTOM_DOMAIN'].strip(" / ")
        return f"{request.scheme}://{custom_domain}/{path}"

    return request.build_absolute_uri(f'/{path}')


def get_sha256_multihash(content):
    '''Get the sha2-256 multihash of the bytes content

    Args:
        content: bytes

    Returns:
        sha256 multihash string
    '''
    digest = hashlib.sha256(content).digest()
    return multihash.to_hex_string(multihash.encode(digest, 'sha2-256'))


def create_multihash(digest, hash_type):
    '''Returns a multihash from a digest

    Args:
        digest: string
        hash_type: string
            hash type sha2-256

    Returns: multihash
        multihash
    '''
    return multihash.decode(multihash.encode(multihash.from_hex_string(digest), hash_type))


def create_multihash_string(digest, hash_code):
    '''Returns a multihash string from a digest

    Args:
        digest: string
        hash_code: string | int
            hash code sha2-256

    Returns: string
        multihash string
    '''
    return multihash.to_hex_string(multihash.encode(digest, hash_code))


def parse_multihash(multihash_string):
    '''Parse a multihash string

    Args:
        multihash_string: string
            multihash string to parse

    Returns.
        Multihash object

    Raises:
        TypeError: if incoming data is not a string
        ValueError: if the incoming data is not a valid multihash
    '''
    return multihash.decode(multihash.from_hex_string(multihash_string))


def harmonize_post_get_for_search(request):
    '''Harmonizes the request of GET and POST for the search endpoint

    Args:
        request: QueryDict

    Returns: Copy of the harmonized QueryDict
    '''
    # POST
    if request.method == 'POST':
        query_param = request.data.copy()
        if 'bbox' in query_param:
            query_param['bbox'] = json.dumps(query_param['bbox']).strip('[]')  # to string
        if 'query' in query_param:
            query_param['query'] = json.dumps(query_param['query'])  # to string

    # GET
    else:
        query_param = request.GET.copy()
        if 'ids' in query_param:
            query_param['ids'] = query_param['ids'].split(',')  # to array
        if 'collections' in query_param:
            query_param['collections'] = query_param['collections'].split(',')  # to array
        if 'intersects' in query_param:
            query_param['intersects'] = json.loads(query_param['intersects'])

        # Forecast properties can only be filtered with method POST.
        # Decision was made as `:` need to be url encoded and (at least for now) we do not need to
        # support forecast filtering in the GET request.
        if 'forecast:reference_datetime' in query_param:
            del query_param['forecast:reference_datetime']
        if 'forecast:horizon' in query_param:
            del query_param['forecast:horizon']
        if 'forecast:duration' in query_param:
            del query_param['forecast:duration']
        if 'forecast:variable' in query_param:
            del query_param['forecast:variable']
        if 'forecast:perturbed' in query_param:
            del query_param['forecast:perturbed']
    return query_param


def get_query_params(url, keys):
    '''Get URL query parameters by keys

    Args:
        url: string
            url to parse and retrieve query parameter
        keys: string | [string]
            query parameter key(s) to retrieve
    Returns: string | [string]
        Query parameter value(s)
    '''
    (scheme, netloc, path, query, fragment) = parse.urlsplit(url)
    query_dict = parse.parse_qs(query, keep_blank_values=True)
    if isinstance(keys, str):
        return query_dict.get(keys, None)
    return [query_dict.get(key, None) for key in keys if key]


def remove_query_params(url, keys):
    """
    Given a URL and a key/val pair, remove an item(s) in the query
    parameters of the URL, and return the new URL.

    Args:
        url: string
            url to parse and retrieve query parameter
        keys: string | [string]
            query parameter key(s) to remove
    Returns: string
        New URL string
    """
    (scheme, netloc, path, query, fragment) = parse.urlsplit(url)
    query_dict = parse.parse_qs(query, keep_blank_values=True)
    if isinstance(keys, str):
        query_dict.pop(keys, None)
    else:
        [query_dict.pop(key, None) for key in keys if key]  # pylint: disable=expression-not-assigned

    query = parse.urlencode(sorted(query_dict.items()), doseq=True)
    return parse.urlunsplit((scheme, netloc, path, query, fragment))


# This class is also used in service-control. Ensure that any changes made here are reflected there
# as well.
class CustomBaseCommand(BaseCommand):
    """
    A custom Django management command that adds proper support for logging.

    Example how to subclass:

        class MyCommand(CustomBaseCommand):

            def add_arguments(self, parser: CommandParser) -> None:
                super().add_arguments(parser)
                parser.add_argument('--flag', action='store_true')

            def handle(self, *args: Any, **options: dict['str', Any]) -> None:
                if options['flag']:  # or self.options['flag']
                    self.print('flag was set')
                self.print_success('done')

    """

    def __init__(
        self,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        no_color: bool = False,
        force_color: bool = False
    ):
        super().__init__(stdout, stderr, no_color, force_color)
        self.logger = logging.getLogger(self.__module__)
        self.options: dict['str', Any] = {}

    def add_arguments(self, parser: CommandParser) -> None:
        """
        Entry point for add custom arguments. Options will also be available as self.options during
        handle.

        Subclasses may want to extend this method.
        """

        parser.add_argument('--logger', action='store_true', help='use logger configuration')

    def handle(self, *args: Any, **options: dict['str', Any]) -> None:
        """
        The actual logic of the command.

        Subclasses must implement this method.
        """

        raise NotImplementedError("subclasses of CustomBaseCommand must provide a handle() method")

    def execute(self, *args: Any, **options: dict['str', Any]) -> None:
        """ Try to execute the command and log any exceptions if the logger is configured. """

        self.options = options
        if self.options['logger']:
            try:
                super().execute(*args, **options)
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.print_error(e, exc_info=True)
        else:
            super().execute(*args, **options)

    def print(self, message: str, *args: Any, level: int = 2, **kwargs: Any) -> None:
        if self.options['verbosity'] >= level:
            if self.options['logger']:
                self.logger.info(message, *args, **kwargs)
            else:
                if len(kwargs) > 0:
                    message = message + " " + ", ".join(
                        f"{key}={value}" for key, value in kwargs.items()
                    )
                self.stdout.write(message % (args))

    def print_warning(self, message: str, *args: Any, level: int = 1, **kwargs: Any) -> None:
        if self.options['verbosity'] >= level:
            if self.options['logger']:
                self.logger.warning(message, *args, **kwargs)
            else:
                if len(kwargs) > 0:
                    message = message + " " + ", ".join(
                        f"{key}={value}" for key, value in kwargs.items()
                    )
                self.stdout.write(self.style.WARNING(message % (args)))

    def print_success(self, message: str, *args: Any, level: int = 1, **kwargs: Any) -> None:
        if self.options['verbosity'] >= level:
            if self.options['logger']:
                self.logger.info(message, *args, **kwargs)
            else:
                if len(kwargs) > 0:
                    message = message + " " + ", ".join(
                        f"{key}={value}" for key, value in kwargs.items()
                    )
                self.stdout.write(self.style.SUCCESS(message % (args)))

    def print_error(self, message: str | Exception, *args: Any, **kwargs: Any) -> None:
        if self.options['logger']:
            self.logger.error(message, *args, **kwargs)
        else:
            message = str(message)
            if len(kwargs) > 0:
                message = message + "\n" + ", ".join(
                    f"{key}={value}" for key, value in kwargs.items()
                )
            self.stderr.write(self.style.ERROR(message % (args)))


def geometry_from_bbox(bbox):
    '''Returns a Geometry from a bbox

    Args:
        bbox: string
            bbox as string comma separated or as float list

    Returns:
        Geometry

    Raises:
        ValueError, IndexError, GDALException, NotImplementedException
    '''
    list_bbox_values = bbox.split(',')
    if len(list_bbox_values) == 6:
        # According to stac search extension the bbox may contain 6 values to represent
        # 3-dimensional bounding box. As the current implementation does not support this,
        # return 501 Not Implemented.
        raise NotImplementedException(detail='3-dimensional bbox is currently not supported')
    if len(list_bbox_values) != 4:
        raise ValueError('A bbox is based of four values')
    try:
        list_bbox_values = list(map(Decimal, list_bbox_values))
    except InvalidOperation as exc:
        raise ValueError(f'Cannot convert list {list_bbox_values} to bbox') from exc

    if (list_bbox_values[0] == list_bbox_values[2] and list_bbox_values[1] == list_bbox_values[3]):
        bbox_geometry = Point(list_bbox_values[:2])
    else:
        bbox_geometry = Polygon.from_bbox(list_bbox_values)

    # if large values, SRID is LV95. The default SRID is 4326
    if list_bbox_values[0] > 360:
        bbox_geometry.srid = 2056
    else:
        bbox_geometry.srid = 4326

    if not bbox_geometry.valid:
        raise ValueError(f'{bbox_geometry.valid_reason} for bbox with {bbox_geometry.wkt}')

    return bbox_geometry


def get_api_version(request) -> API_VERSION:
    '''get the api version from the request, default to v1'''
    if request is not None and hasattr(request, 'resolver_match'):
        if request.resolver_match.namespace in ('v0.9', 'test_v0.9'):
            return API_VERSION.v09
    return API_VERSION.v1


def get_stac_version(request):
    return '0.9.0' if get_api_version(request) == API_VERSION.v09 else '1.0.0'


def is_api_version_1(request):
    return get_api_version(request) == API_VERSION.v1


def get_url(request, view, args=None):
    '''Get an full url based on a view name'''
    ns = request.resolver_match.namespace
    if ns is not None:
        view = ns + ':' + view
    return request.build_absolute_uri(reverse(view, current_app=ns, args=args))


def get_browser_url(request, view, collection=None, item=None):
    if settings.STAC_BROWSER_HOST:
        base = f'{settings.STAC_BROWSER_HOST}/{settings.STAC_BROWSER_BASE_PATH}'
    else:
        base = request.build_absolute_uri(f'/{settings.STAC_BROWSER_BASE_PATH}')

    if view == 'browser-catalog':
        return f'{base}#/'
    if view == 'browser-collection' and collection:
        return f'{base}#/collections/{collection}'
    if view == 'browser-item' and collection and item:
        return f'{base}#/collections/{collection}/items/{item}'
    logger.error(
        'Failed to return STAC browser url for view=%s, collection=%s, item=%s, use then url=%s',
        view,
        collection,
        item,
        base
    )
    return base


def is_valid_b64(value):
    '''Check if the value is a valid b64 encoded string

    Args:
        value: string
            Value to check

    Returns:
        bool - True if valid, False otherwise
    '''
    if not isinstance(value, str):
        return False
    try:
        b64decode(value)
    except (ValueError) as err:
        logger.debug('Invalid b64 value %s: %s', value, err)
        return False
    return True


def get_s3_cache_control_value(cache_control_header):
    if cache_control_header:
        return cache_control_header
    # Else use default cache settings
    return f'max-age={settings.STORAGE_ASSETS_CACHE_SECONDS}, public'


def select_s3_bucket(collection_name) -> AVAILABLE_S3_BUCKETS:
    """Select the s3 bucket based on the collection name

    Select the correct s3 bucket based on matching patterns with the collection
    name
    """
    patterns = settings.MANAGED_BUCKET_COLLECTION_PATTERNS

    for pattern in patterns:
        if collection_name.startswith(pattern):
            return AVAILABLE_S3_BUCKETS.managed

    return AVAILABLE_S3_BUCKETS.legacy


def parse_cache_control_header(cache_control_header):
    '''Parse the Cache-Control header into a dict of settings.
    Args:
        cache_control_header (str): The Cache-Control header value as in HTTP spec.
    Returns:
        dict: A dict of cache settings to be used in django.utils.cache.patch_cache_control.
    '''
    parts = [i.strip() for i in cache_control_header.split(',')]
    args = {i.split('=')[0].strip(): i.split('=')[-1].strip() for i in parts if i}
    return {k: True if v == k else v for k, v in args.items()}
