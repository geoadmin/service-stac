import json
import logging
from datetime import timedelta
from pprint import pformat
from urllib.parse import urlparse

from django.contrib.gis.geos.geometry import GEOSGeometry
from django.test import TestCase

from stac_api.utils import fromisoformat
from stac_api.utils import get_link
from stac_api.utils import get_provider

from tests.utils import get_http_error_description

logger = logging.getLogger(__name__)


class StacBaseTestCase(TestCase):

    # we keep the TestCase nomenclature here therefore we disable the pylint invalid-name
    def assertStatusCode(self, code, response, msg=None):  # pylint: disable=invalid-name
        '''Assert the HTTP Status Code

        Check the status code, if the status code is a >= 400 then the response body is also check
        against the `code` and `description` keys.

        Args:
            code: int
                Expected HTTP code
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

        self.assertEqual(code, response.status_code, msg=get_error_msg(response.status_code))
        if code in [412, 304]:
            # HTTP 412 Precondition Failed and 304 Not Modified doesn't have a body.
            self.assertEqual(b'', response.content)
        elif code >= 400:
            self.assertIn('code', json_data.keys(), msg="'code' is missing from response")
            self.assertIn(
                'description', json_data.keys(), msg="'description' is missing from response"
            )
            self.assertTrue(
                isinstance(json_data['description'], (list, str, dict)),
                msg=f"Description wrong type: {type(json_data['description'])}"
            )
            self.assertEqual(code, json_data['code'], msg="invalid response code")

    def check_header_etag(self, etag, response):
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

    def check_header_location(self, expected_path, response):
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

    def check_stac_item(self, expected, current, ignore=None):
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

    def check_stac_asset(self, expected, current, ignore=None):
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

    def _check_stac_dictsubset(self, parent_path, expected, current, ignore=None):
        for key, value in expected.items():
            path = f'{parent_path}.{key}'

            # We need to remove the stac_extensions from here when BGDIINF_SB-1410 is implemented
            if (ignore and key in ignore) or key in ['stac_extensions']:
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
            self.assertIsNotNone(current_link, msg=f'{path}: Link {link} is missing in current')
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
        if key in ['eo:gsd'] and parent_path.split('.')[-1] != 'summaries':
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
            # created and updated time are automatically set therefore don't do an exact
            # test as we can't guess the exact time.
            self.assertAlmostEqual(
                fromisoformat(value),
                fromisoformat(current[key]),
                delta=timedelta(seconds=1),
                msg=f'{path}: current datetime value is not equal to the expected'
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
