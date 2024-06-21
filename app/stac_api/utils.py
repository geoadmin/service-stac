import hashlib
import json
import logging
import math
import re
from base64 import b64decode
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from decimal import InvalidOperation
from enum import Enum
from urllib import parse

import boto3
import multihash
from botocore.client import Config

from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.urls import reverse

logger = logging.getLogger(__name__)

AVAILABLE_S3_BUCKETS = Enum('AVAILABLE_S3_BUCKETS', ['MANAGED', 'LEGACY'])


def isoformat(date_time):
    '''Return a datetime string in isoformat using 'Z' as timezone instead of '+00:00'
    '''
    return date_time.isoformat().replace('+00:00', 'Z')


def fromisoformat(date_time):
    '''Return a datetime object from a isoformated datetime string
    '''
    return datetime.fromisoformat(date_time.replace('Z', '+00:00'))


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


def get_s3_resource(s3_bucket: AVAILABLE_S3_BUCKETS = AVAILABLE_S3_BUCKETS.LEGACY):
    '''Returns an AWS S3 resource

    The authentication with the S3 server is configured via the AWS_ACCESS_KEY_ID and
    AWS_SECRET_ACCESS_KEY environment variables.

    Returns:
        AWS S3 resource
    '''

    config = get_aws_settings(s3_bucket)
    endpoint_url = config['S3_ENDPOINT_URL']

    return boto3.resource('s3', endpoint_url=endpoint_url, config=Config(signature_version='s3v4'))


def get_s3_client(s3_bucket: AVAILABLE_S3_BUCKETS = AVAILABLE_S3_BUCKETS.LEGACY):
    '''Returns an AWS S3 client


    Returns:
        AWS S3 client
    '''

    conf = get_aws_settings(s3_bucket)

    client = boto3.client(
        's3',
        endpoint_url=conf['S3_ENDPOINT_URL'],
        region_name=conf['S3_REGION_NAME'],
        config=Config(signature_version=conf['S3_SIGNATURE_VERSION']),
        aws_access_key_id=conf['ACCESS_KEY_ID'],
        aws_secret_access_key=conf['SECRET_ACCESS_KEY']
    )

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
    if settings.AWS_LEGACY['S3_CUSTOM_DOMAIN']:
        # By definition we should not mixed up HTTP Scheme (HTTP/HTTPS) within our service,
        # although the Assets file are not served by django we configure it with the same scheme
        # as django that's why it is kind of safe to use the django scheme.
        return f"{request.scheme}://{settings.AWS_LEGACY['S3_CUSTOM_DOMAIN'].strip(" / ")}/{path}"

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


class CommandHandler():
    '''Base class for management command handler

    This class add proper support for printing to the console for management command
    '''

    def __init__(self, command, options):
        self.options = options
        self.verbosity = options['verbosity']
        self.stdout = command.stdout
        self.stderr = command.stderr
        self.style = command.style
        self.command = command

    def print(self, message, *args, level=2):
        if self.verbosity >= level:
            self.stdout.write(message % (args))

    def print_warning(self, message, *args, level=1):
        if self.verbosity >= level:
            self.stdout.write(self.style.WARNING(message % (args)))

    def print_success(self, message, *args, level=1):
        if self.verbosity >= level:
            self.stdout.write(self.style.SUCCESS(message % (args)))

    def print_error(self, message, *args):
        self.stderr.write(self.style.ERROR(message % (args)))


def geometry_from_bbox(bbox):
    '''Returns a Geometry from a bbox

    Args:
        bbox: string
            bbox as string comma separated or as float list

    Returns:
        Geometry

    Raises:
        ValueError, IndexError, GDALException
    '''
    list_bbox_values = bbox.split(',')
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

    if not bbox_geometry.valid:
        raise ValueError(f'{bbox_geometry.valid_reason} for bbox with {bbox_geometry.wkt}')

    return bbox_geometry


def get_stac_version(request):
    version = 'v1'
    if request is not None and hasattr(request, 'resolver_match'):
        version = request.resolver_match.namespace
    return '0.9.0' if version == 'v0.9' else '1.0.0'


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


def get_dynamic_max_age_value(update_interval):
    '''Get the max_age value for dynamic cache based on `update_interval` DB field

    -       update_interval < 0  then use default cache settings
    -  0 <= update_interval < 10 then no cache
    - 10 <= update_interval then log10(update_interval)*log9(update_interval)
    Args:
        update_interval: int
            Value of the DB field `update_interval`

    Returns:
        int - Cache control max_age, or -1 to use default cache settings
    '''
    threshold_no_cache = 10
    max_threshold = 60 * 60  # 1h
    if 0 <= update_interval < threshold_no_cache:
        return 0  # means never cache

    if threshold_no_cache <= update_interval < max_threshold:
        return int(math.log(update_interval, 10) * math.log(update_interval, 9))

    if max_threshold <= update_interval:
        raise ValueError('update_interval should not be more than 1h')

    return -1  # means use default cache settings


def get_s3_cache_control_value(update_interval):
    max_age = get_dynamic_max_age_value(update_interval)

    if max_age == 0:
        return 'max-age=0, no-cache, no-store, must-revalidate, private'

    if max_age > 0:
        return f'max-age={max_age}, public'

    return f'max-age={settings.STORAGE_ASSETS_CACHE_SECONDS}, public'


def select_s3_bucket(collection_name) -> AVAILABLE_S3_BUCKETS:
    """Select the s3 bucket based on the collection name

    Select the correct s3 bucket based on matching patterns with the collection
    name
    """
    patterns = settings.MANAGED_BUCKET_COLLECTION_PATTERNS

    for pattern in patterns:
        match = re.fullmatch(pattern, collection_name)
        if match is not None:
            return AVAILABLE_S3_BUCKETS.MANAGED

    return AVAILABLE_S3_BUCKETS.LEGACY


def get_aws_settings(s3_bucket: AVAILABLE_S3_BUCKETS = AVAILABLE_S3_BUCKETS.LEGACY):

    if s3_bucket == AVAILABLE_S3_BUCKETS.LEGACY:
        return settings.AWS_LEGACY

    return settings.AWS_MANAGED
