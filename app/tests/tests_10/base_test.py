import json
import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from datetime import datetime
from pprint import pformat
from urllib.parse import urlparse

from django.contrib.gis.geos.geometry import GEOSGeometry
from django.db import connections
from django.test import TestCase
from django.test import TransactionTestCase

from stac_api.utils import fromisoformat
from stac_api.utils import get_link
from stac_api.utils import get_provider
from stac_api.utils import isoformat
from stac_api.utils import utc_aware

from tests.utils import get_http_error_description

logger = logging.getLogger(__name__)

VERSION_SHORT = 'v1'
STAC_BASE_V = f'api/stac/{VERSION_SHORT}'
TEST_LINK_ROOT_HREF = f'http://testserver/api/stac/{VERSION_SHORT}'
TEST_LINK_ROOT = {'rel': 'root', 'href': f'{TEST_LINK_ROOT_HREF}/'}
STAC_VERSION = '1.0.0'


class StacTestMixin:
    """Adds some useful checks for STAC API unittesting
    """

    # we keep the TestCase nomenclature here therefore we disable the pylint invalid-name
    def assertStatusCode(self, code, response, msg=None):  # pylint: disable=invalid-name
        '''Assert the HTTP Status Code

        Check the status code, if the status code is a >= 400 then the response body is also check
        against the `code` and `description` keys.

        Args:
            code: int | [int]
                Expected HTTP code(s)
            response: HttpResponse
                HTTP Response object to check
			msg: string
				Error message to display when the assertion failed
        '''
        try:
            json_data = response.json()
        except (TypeError, ValueError) as err:
            json_data = {}

        def get_error_msg(code):
            if code >= 400 and not msg:
                return get_http_error_description(json_data)
            if msg:
                return msg
            return 'Wrong status code'

        codes = code if isinstance(code, list) else [code]
        self.assertIn(response.status_code, codes, msg=get_error_msg(response.status_code))
        if response.status_code in [412, 304]:
            # HTTP 412 Precondition Failed and 304 Not Modified doesn't have a body.
            self.assertEqual(b'', response.content)
        elif response.status_code >= 400:
            self.assertIn('code', json_data.keys(), msg="'code' is missing from response")
            self.assertIn(
                'description', json_data.keys(), msg="'description' is missing from response"
            )
            self.assertTrue(
                isinstance(json_data['description'], (list, str, dict)),
                msg=f"Description wrong type: {type(json_data['description'])}"
            )
            self.assertEqual(response.status_code, json_data['code'], msg="invalid response code")

    def assertCacheControl(self, response, max_age=None, no_cache=False):  # pylint: disable=invalid-name
        '''Assert that Cache-Control header is present and correct

        Args:
            response: HttpResponse
                Response to check
            max_age: int | None
                Check that the header is `public, max-age=x`
            no_cache: bool
                Check that the header is `max-age=0, no-cache, no-store, must-revalidate, private`
        '''
        self.assertTrue(response.has_header('Cache-Control'), msg="Cache-Control header missing")
        if no_cache:
            self.assertEqual(
                response['Cache-Control'],
                'max-age=0, no-cache, no-store, must-revalidate, private'
            )
        elif max_age is not None:
            self.assertEqual(response['Cache-Control'], f'max-age={max_age}, public')

    def assertEtagHeader(self, etag, response):  # pylint: disable=invalid-name
        '''Check for the ETag Header

        Args:
            etag: string | None
                Expected ETag value or None if the value cannot be checked (e.g. the ETag changed
                for each test call).
            response: HttpResponse
                HTTP response object
        '''
        self.assertTrue(response.has_header('ETag'), msg="ETag header missing")
        self.assertTrue(
            response['ETag'].startswith('"') and response['ETag'].endswith('"'),
            msg="ETag is not enclosed in double quotes"
        )
        if etag is not None:
            self.assertEqual(etag, response['ETag'], msg="ETag header missmatch")

    def assertLocationHeader(self, expected_path, response):  # pylint: disable=invalid-name
        '''Check the Location Header

        Args:
            expected_path: string
                expected path in location header
            response:
                request response
        '''
        self.assertTrue(response.has_header('Location'), msg="Location header is missing")
        self.assertEqual(
            expected_path, urlparse(response['Location']).path, msg="Wrong location path"
        )

    def assertCors(self, response):  # pylint: disable=invalid-name
        for header, value in {
            'Access-Control-Allow-Headers': 'Content-Type,Accept',
            'Access-Control-Allow-Methods': 'GET,HEAD',
            'Access-Control-Allow-Origin': '*'
        }.items():
            self.assertTrue(response.has_header(header), msg=f"{header}: header is missing")
            self.assertEqual(response[header], value)

    def check_stac_collection(self, expected, current, ignore=None):
        '''Check a STAC Collection data

        Check if the `current` Collection data match the `expected`. This check is a subset check
        which means that if a value is missing from `current`, then it raises a Test Assert, while
        if a value is in `current` but not in `expected`, the test passed. The functions knows also
        the STAC Spec and does some check based on it.

        Args:
            expected: dict
                Expected STAC Collection
            current: dict
                Current STAC Collection to test
            ignore: list(string) | None
                List of keys to ignore in the test
        '''
        if ignore is None:
            ignore = []
        self._check_stac_dictsubset('collection', expected, current, ignore)
        # check required fields
        for key, value in [
            ('stac_version', '1.0.0'),
            ('crs', ['http://www.opengis.net/def/crs/OGC/1.3/CRS84']),
            ('itemType', 'Feature'),
            ('type', 'Collection')
        ]:
            self.assertIn(key, current)
            self.assertEqual(value, current[key])
        for key in ['id', 'extent', 'summaries', 'links', 'description', 'license']:
            self.assertIn(key, current, msg=f'Collection {key} is missing')
        for date_field in ['created', 'updated']:
            self.assertIn(date_field, current, msg=f'Collection {date_field} is missing')
            self.assertTrue(
                fromisoformat(current[date_field]),
                msg=f"The collection field {date_field} has an invalid date"
            )
        name = current['id']
        links = [
            {
                'rel': 'self',
                'href': f'{TEST_LINK_ROOT_HREF}/collections/{name}',
            },
            TEST_LINK_ROOT,
            {
                'rel': 'parent',
                'href': f'{TEST_LINK_ROOT_HREF}/',
            },
            {
                'rel': 'items',
                'href': f'{TEST_LINK_ROOT_HREF}/collections/{name}/items',
            },
        ]
        self._check_stac_links('item.links', links, current['links'])

    def check_stac_item(self, expected, current, collection, ignore=None):
        '''Check a STAC Item data

        Check if the `current` Item data match the `expected`. This check is a subset check
        which means that if a value is missing from `current`, then it raises a Test Assert, while
        if a value is in `current` but not in `expected`, the test passed. The functions knows also
        the STAC Spec and does some check based on it.

        Args:
            expected: dict
                Expected STAC Item
            current: dict
                Current STAC Item to test
            ignore: list(string) | None
                List of keys to ignore in the test
        '''
        if ignore is None:
            ignore = []
        self._check_stac_dictsubset('item', expected, current, ignore=ignore)

        # check required fields
        for key, value in [('stac_version', '1.0.0'), ('type', 'Feature')]:
            self.assertIn(key, current)
            self.assertEqual(value, current[key])
        for key in ['id', 'bbox', 'links', 'properties', 'assets', 'geometry']:
            self.assertIn(key, current, msg=f'Item {key} is missing')
        for date_field in ['created', 'updated']:
            self.assertIn(
                date_field, current['properties'], msg=f'Item properties.{date_field} is missing'
            )
            self.assertTrue(
                fromisoformat(current['properties'][date_field]),
                msg=f"The item field {date_field} has an invalid date"
            )

        name = current['id']
        links = [
            {
                'rel': 'self',
                'href': f'{TEST_LINK_ROOT_HREF}/collections/{collection}/items/{name}',
            },
            TEST_LINK_ROOT,
            {
                'rel': 'parent',
                'href': f'{TEST_LINK_ROOT_HREF}/collections/{collection}',
            },
            {
                'rel': 'collection',
                'href': f'{TEST_LINK_ROOT_HREF}/collections/{collection}',
            },
        ]
        self._check_stac_links('item.links', links, current['links'])

    def check_stac_asset(self, expected, current, collection, item, ignore=None):
        '''Check a STAC Asset data

        Check if the `current` Asset data match the `expected`. This check is a subset check
        which means that if a value is missing from `current`, then it raises a Test Assert, while
        if a value is in `current` but not in `expected`, the test passed. The functions knows also
        the STAC Spec and does some check based on it.

        Args:
            expected: dict
                Expected STAC Asset
            current: dict
                Current STAC Asset to test
            ignore: list(string) | None
                List of keys to ignore in the test
        '''
        if ignore is None:
            ignore = []
        self._check_stac_dictsubset('asset', expected, current, ignore=ignore)

        # check required fields
        for key in ['links', 'id', 'type', 'href']:
            if key in ignore:
                logger.info('Ignoring key %s in asset', key)
                continue
            self.assertIn(key, current, msg=f'Asset {key} is missing')
        for date_field in ['created', 'updated']:
            if key in ignore:
                logger.info('Ignoring key %s in asset', key)
                continue
            self.assertIn(date_field, current, msg=f'Asset {date_field} is missing')
            self.assertTrue(
                fromisoformat(current[date_field]),
                msg=f"The asset field {date_field} has an invalid date"
            )
        if 'links' not in ignore:
            name = current['id']
            links = [
                {
                    'rel': 'self',
                    'href':
                        f'{TEST_LINK_ROOT_HREF}/collections/{collection}/items/{item}/assets/{name}'
                },
                TEST_LINK_ROOT,
                {
                    'rel': 'parent',
                    'href': f'{TEST_LINK_ROOT_HREF}/collections/{collection}/items/{item}',
                },
                {
                    'rel': 'item',
                    'href': f'{TEST_LINK_ROOT_HREF}/collections/{collection}/items/{item}',
                },
                {
                    'rel': 'collection',
                    'href': f'{TEST_LINK_ROOT_HREF}/collections/{collection}',
                },
            ]
            self._check_stac_links('asset.links', links, current['links'])

    def _check_stac_dictsubset(self, parent_path, expected, current, ignore=None):
        for key, value in expected.items():
            path = f'{parent_path}.{key}'

            if (ignore and key in ignore):
                if key not in ['item', 'created', 'updated']:
                    logger.warning('Ignoring key %s in %s', key, path)
                else:
                    logger.info('Ignoring key %s in %s', key, path)
                continue

            self.assertIn(key, current, msg=f'{parent_path}: Key {key} is missing')

            self._check_type(parent_path, key, value, current)

            self._check_value(path, key, value, current, ignore)

    def _check_stac_list(self, parent_path, expected, current):
        for i, value in enumerate(expected):
            path = f'{parent_path}.{i}'
            if isinstance(value, dict):
                self._check_stac_dictsubset(path, value, current[i])
            elif isinstance(value, list):
                self._check_stac_list(path, value, current[i])
            elif i >= len(current):
                self.fail(f'{parent_path}: List index {i} is out of bound: {expected} != {current}')
            else:
                self.assertEqual(
                    value,
                    current[i],
                    msg=f'{parent_path}: List index {i} in current is not equal to the expected'
                )

    def _check_stac_links(self, parent_path, expected, current):
        # sort links by rel
        expected = list(sorted(expected, key=lambda link: link['rel']))
        current = list(sorted(current, key=lambda link: link['rel']))
        logger.debug('Expected links:\n%s', pformat(expected))
        logger.debug('Current links:\n%s', pformat(current))
        for i, link in enumerate(expected):
            path = f'{parent_path}.{i}'
            current_link = get_link(current, link['rel'])
            self.assertIsNotNone(
                current_link, msg=f'{path}: Link {link} is missing in current links {current}'
            )
            for key, value in link.items():
                self.assertIn(
                    key, current_link, msg=f'key {key} is missing in current link {current_link}'
                )
                if key == 'href':
                    self.assertEqual(
                        urlparse(value).path,
                        urlparse(current_link[key]).path,
                        msg=f'{path}[{key}]: value does not match in link {current_link}'
                    )
                else:
                    self.assertEqual(
                        value,
                        current_link[key],
                        msg=f'{path}[{key}]: value does not match in link {current_link}'
                    )

    def _check_stac_providers(self, parent_path, expected, current):
        # sort providers by name
        expected = list(sorted(expected, key=lambda provider: provider['name']))
        current = list(sorted(current, key=lambda provider: provider['name']))
        logger.debug('Expected providers:\n%s', pformat(expected))
        logger.debug('Current providers:\n%s', pformat(current))
        for i, provider in enumerate(expected):
            path = f'{parent_path}.{i}'
            current_provider = get_provider(current, provider['name'])
            self.assertIsNotNone(
                current_provider, msg=f'{path}: Provider {provider} is missing in current'
            )
            for key, value in provider.items():
                self.assertIn(
                    key,
                    current_provider,
                    msg=f'key {key} is missing in current provider {current_provider}'
                )
                self.assertEqual(
                    value,
                    current_provider[key],
                    msg=f'{path}[{key}]: value does not match in provider {current_provider}'
                )

    def _check_stac_geometry(self, expected, current):
        if isinstance(expected, dict):
            expected = GEOSGeometry(json.dumps(expected))
        elif isinstance(expected, str):
            expected = GEOSGeometry(expected)
        elif not isinstance(expected, GEOSGeometry):
            self.fail(
                f"Invalid expected geometry type: {expected}: "
                "should be dict, string or GEOSGeometry"
            )

        if isinstance(current, dict):
            current = GEOSGeometry(json.dumps(current))
        elif isinstance(current, str):
            current = GEOSGeometry(current)
        elif not isinstance(current, GEOSGeometry):
            self.fail(
                f"Invalid current geometry type: {current}: "
                "should be dict, string or GEOSGeometry"
            )

        self.assertEqual(expected, current, msg="Geometry are not equal")

    def _check_type(self, parent_path, key, value, current):
        if key in ['gsd'] and parent_path.split('.')[-1] != 'summaries':
            self.assertEqual(
                type(float(value)),
                type(current[key]),
                msg=f'{parent_path}: key {key} type does not match'
            )
        elif key not in ['geometry']:
            self.assertTrue(
                isinstance(current[key], type(value)),
                msg=f'{parent_path}: key {key} type does not match: '
                f'expected {type(value)}, has {type(current[key])}'
            )

    def _check_value(self, path, key, value, current, ignore):
        if key == 'geometry':
            self._check_stac_geometry(value, current[key])
        elif isinstance(value, dict):
            self._check_stac_dictsubset(path, value, current[key], ignore)
        elif isinstance(value, list):
            if key == 'links':
                self._check_stac_links(path, value, current[key])
            elif key == 'providers':
                self._check_stac_providers(path, value, current[key])
            elif key in ['bbox']:
                self._check_stac_list(path, value, current[key])
            else:
                self._check_stac_list(path, sorted(value), sorted(current[key]))
        elif key in ['created', 'updated']:
            # Created and updated time are automatically set therefore don't do an exact
            # test as we can't guess the exact time. So we just check these timestamps
            # are from after the start of the test and before "now".
            self.assertLessEqual(
                value,
                current[key],
                msg=f'{path}: current datetime value is before test start time'
            )
            now = isoformat(utc_aware(datetime.now()))
            self.assertGreaterEqual(
                now, current[key], msg=f'{path}: current datetime value is after test end time'
            )
        elif key == 'href':
            self.assertEqual(
                urlparse(value).path,
                urlparse(current[key]).path,
                msg=f'{path}: value does not match in href {current[key]}'
            )
        else:
            self.assertEqual(
                value, current[key], msg=f'{path}: current value is not equal to the expected'
            )


class StacBaseTestCase(TestCase, StacTestMixin):
    """Django TestCase with additional STAC check methods"""


class StacBaseTransactionTestCase(TransactionTestCase, StacTestMixin):
    """Django TransactionTestCase with additional STAC check methods
    """

    @staticmethod
    def on_done(future):
        # Because each thread has a db connection, we call close_all() when the thread is
        # terminated. This is needed because the thread are not managed by django here but
        # by us.
        connections.close_all()

    def run_parallel(self, workers, func):
        errors = []
        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for worker in range(workers):
                future = executor.submit(func, worker)
                future.add_done_callback(self.on_done)
                futures[future] = worker
            for future in as_completed(futures):
                try:
                    response = future.result()
                except Exception as exc:  # pylint: disable=broad-except
                    errors.append((futures[future], str(exc)))
                else:
                    results.append((futures[future], response))

        self.assertEqual(
            len(results) + len(errors),
            workers,
            msg='Number of results/errors doesn\'t match the number of worker'
        )

        for worker, error in errors:
            self.fail(msg=f'Worker {worker} failed: {error}')

        return results, errors
