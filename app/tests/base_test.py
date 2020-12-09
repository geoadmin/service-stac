import logging
from datetime import timedelta
from pprint import pformat
from urllib.parse import urlparse

from django.test import TestCase

from stac_api.utils import fromisoformat
from stac_api.utils import get_link

from tests.utils import get_http_error_description

logger = logging.getLogger(__name__)


class StacBaseTestCase(TestCase):

    # we keep the TestCase nomenclature here therefore we disable the pylint invalid-name
    def assertStatusCode(self, code, response):  # pylint: disable=invalid-name
        json_data = response.json()
        self.assertEqual(code, response.status_code, msg=get_http_error_description(json_data))
        if code >= 400:
            self.assertIn('code', json_data.keys(), msg="'code' is missing from response")
            self.assertIn(
                'description', json_data.keys(), msg="'description' is missing from response"
            )
            self.assertEqual(code, json_data['code'], msg="invalid response code")

    def check_stac_collection(self, expected, current, ignore=None):
        if ignore is None:
            ignore = []
        self._check_stac_dictsubset('collection', expected, current, ignore)

    def check_stac_item(self, expected, current, ignore=None):
        if ignore is None:
            ignore = []
        self._check_stac_dictsubset('item', expected, current, ignore=ignore + ['href'])

    def check_stac_asset(self, expected, current, ignore=None):
        if ignore is None:
            ignore = []
        self._check_stac_dictsubset('asset', expected, current, ignore=ignore + ['href'])

    def _check_stac_dictsubset(self, parent_path, expected, current, ignore=None):
        for key, value in expected.items():
            path = f'{parent_path}.{key}'
            # We need to remove the stac_extensions from here when BGDIINF_SB-1410 is implemented
            if (ignore and key in ignore) or key in ['stac_extensions']:
                logger.warning('Ignoring key %s in %s', key, path)
                continue
            self.assertIn(key, current, msg=f'{parent_path}: Key {key} is missing')
            if key in ['eo:gsd'] and parent_path.split('.')[-1] != 'summaries':
                self.assertEqual(
                    type(float(value)),
                    type(current[key]),
                    msg=f'{parent_path}: key {key} type does not match'
                )
            else:
                self.assertEqual(
                    type(value),
                    type(current[key]),
                    msg=f'{parent_path}: key {key} type does not match'
                )
            if isinstance(value, dict):
                self._check_stac_dictsubset(path, value, current[key], ignore)
            elif isinstance(value, list):
                if key == 'links':
                    self._check_stac_links(path, value, current[key])
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
            else:
                self.assertEqual(
                    value, current[key], msg=f'{path}: current value is not equal to the expected'
                )

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
