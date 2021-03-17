import hashlib
import json
import logging
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from urllib import parse

import boto3
import multihash
from botocore.client import Config

from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon

logger = logging.getLogger(__name__)


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


def get_s3_resource():
    '''Returns an AWS S3 resource

    Returns:
        AWS S3 resource
    '''
    return boto3.resource(
        's3', endpoint_url=settings.AWS_S3_ENDPOINT_URL, config=Config(signature_version='s3v4')
    )


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
    # AWS_S3_CUSTOM_DOMAIN
    if settings.AWS_S3_CUSTOM_DOMAIN:
        # By definition we should not mixed up HTTP Scheme (HTTP/HTTPS) within our service,
        # although the Assets file are not served by django we configure it with the same scheme
        # as django that's why it is kind of safe to use the django scheme.
        return f'{request.scheme}://{settings.AWS_S3_CUSTOM_DOMAIN.strip("/")}/{path}'

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
            hash type (sha2-256, md5, ...)

    Returns: multihash
        multihash
    '''
    return multihash.decode(multihash.encode(multihash.from_hex_string(digest), hash_type))


def create_multihash_string(digest, hash_code):
    '''Returns a multihash string from a digest

    Args:
        digest: string
        hash_code: string | int
            hash code (sha2-256, md5, ...)

    Returns: string
        multihash string
    '''
    return multihash.to_hex_string(multihash.encode(digest, hash_code))


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
    if (
        Decimal(list_bbox_values[0]) == Decimal(list_bbox_values[2]) and
        Decimal(list_bbox_values[1]) == Decimal(list_bbox_values[3])
    ):
        bbox_geometry = Point(float(list_bbox_values[0]), float(list_bbox_values[1]))
    else:
        bbox_geometry = Polygon.from_bbox(list_bbox_values)
    return bbox_geometry
