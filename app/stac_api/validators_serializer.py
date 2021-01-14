import logging
from urllib.parse import urlparse

import multihash
import requests
from multihash import from_hex_string
from multihash import to_hex_string

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError

from stac_api.utils import create_multihash
from stac_api.utils import create_multihash_string
from stac_api.utils import get_asset_path

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


def validate_and_parse_href_url(url_prefix, href):
    '''Parse and validate href URL

    Validate the given href which needs to ba a valid URL with the same domain as the given prefix

    Args:
        url_prefix:
            URL prefix to use for domain validation
        href: string
            href url string to parse and validate

    Returns:
        Parse url object

    Raises:
        ValidationError in case of invalid href
    '''
    logger.debug('Validate and parse href url %s, url_prefix=%s', href, url_prefix)
    url_prefix = urlparse(url_prefix)
    try:
        url = urlparse(href)
    except ValueError as error:
        logger.error('Invalid href %s, must be a valid URL', href)
        raise ValidationError({'href': _('Invalid value, must be a valid URL')}) from error

    # the asset should come from the same host
    if url.netloc != url_prefix.netloc:
        logger.error('Invalid href %s, must be on domain %s', href, url_prefix.netloc)
        raise ValidationError({'href': _(f'Invalid value, must be on domain {url_prefix.netloc}')})
    return url


def validate_asset_file(href, attrs):
    '''Validate Asset file

    Validate the Asset file located at href. The file must exist and match the multihash. The file
    hash is retrieved by doing a HTTP HEAD request at href.

    Args:
        href: string
            Asset file href to validate
        expected_multihash: string (optional)
            Asset file expected multihash (must be a sha2-256 multihash !)

    Raises:
        rest_framework.exceptions.ValidationError:
            in case of invalid Asset (asset doesn't exist or hash doesn't match)
        rest_framework.exceptions.APIException:
            in case of other networking errors
    '''
    logger.debug('Validate asset file at %s with attrs %s', href, attrs)
    try:
        response = requests.head(href, timeout=settings.EXTERNAL_SERVICE_TIMEOUT)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
        logger.error('Failed to check if asset exists at href %s, %s', href, error)
        raise ValidationError({'href': _("href location not responding")})
    except requests.exceptions.RequestException as error:
        logger.error('Failed to check if asset exists at href %s, %s', href, error)
        # here we raise for a 500 HTTP error code as this should not happen and is a server issue
        raise APIException({'href': _("Error while checking href existence")})

    logger.debug(
        'Asset file %s HEAD request; status_code=%d, headers=%s',
        href,
        response.status_code,
        response.headers
    )

    if response.status_code == 404:
        logger.error('Asset at href %s doesn\'t exists', href)
        raise ValidationError({'href': _("Asset doesn't exists at href")})

    if response.status_code != 200:
        logger.error(
            'Failed to check Asset at href %s existence; status code=%s',
            href,
            response.status_code
        )
        # here we raise for a 500 HTTP error code as this should not happen and is a server issue
        raise APIException({'href': _("Error while checking href existence")})

    # Get the hash from response
    asset_multihash = None
    asset_sha256 = response.headers.get('x-amz-meta-sha256', None)
    asset_md5 = response.headers.get('etag', '').strip('"')
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
        'Validate asset file checksum at %s with multihash %s/%s, expected %s/%s',
        href,
        to_hex_string(asset_multihash.digest),
        asset_multihash.name,
        to_hex_string(expected_multihash.digest),
        expected_multihash.name
    )

    if asset_multihash.name != expected_multihash.name:
        logger.error(
            'Asset at href %s, with multihash name=%s digest=%s, doesn\'t match the expected '
            'multihash name=%s digest=%s',
            href,
            asset_multihash.name,
            to_hex_string(asset_multihash.digest),
            expected_multihash.name,
            to_hex_string(expected_multihash.digest)
        )
        raise ValidationError(
            code='href',
            detail=_(f"Asset at href {href} has an {asset_multihash.name} multihash while an "
                     f"{expected_multihash.name} multihash is expected")
        )

    if asset_multihash != expected_multihash:
        logger.error(
            'Asset at href %s, with multihash name=%s digest=%s, doesn\'t match the expected '
            'multihash name=%s digest=%s',
            href,
            asset_multihash.name,
            to_hex_string(asset_multihash.digest),
            expected_multihash.name,
            to_hex_string(expected_multihash.digest)
        )
        raise ValidationError(
            code='href',
            detail=_(f"Asset at href {href} with {asset_multihash.name} hash "
                     f"{to_hex_string(asset_multihash.digest)} don't match expected hash "
                     f"{to_hex_string(expected_multihash.digest)}")
        )
