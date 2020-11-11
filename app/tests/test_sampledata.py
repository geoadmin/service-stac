import json
import logging
import os
from pathlib import Path
from pprint import pformat

from django.conf import settings
from django.test import Client
from django.test import TestCase

from stac_api.sample_data import importer

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE
DATADIR = settings.BASE_DIR / 'app/stac_api/sample_data/'


class SampleDataTestCase(TestCase):

    def setUp(self):
        self.client = Client()

        self.maxDiff = None  # pylint: disable=invalid-name

    def test_samples(self):
        for collection_dir in os.scandir(DATADIR):
            if collection_dir.is_dir() and not collection_dir.name.startswith('_'):
                with self.subTest(msg=collection_dir.name, collection_dir=collection_dir):
                    self._test_collection(Path(collection_dir.path))

    def _test_collection(self, collection_dir):
        collection = importer.import_collection(collection_dir)

        with open(collection_dir / 'collection.json') as fd:
            collection_dict = json.load(fd)

        response = self.client.get(f"/{API_BASE}collections/{collection.collection_name}")
        payload = response.json()
        logger.debug('Payload:\n%s', pformat(payload))
        self.assertEqual(200, response.status_code)

        self._test_dict('', collection_dict, payload)

    def _test_dict(self, parent_path, dct, payload):
        for key, value in dct.items():
            path = f'{parent_path}[{key}]'
            self.assertIn(key, payload, msg=f'{parent_path}: Key {key} is not in payload')
            self.assertEqual(
                type(value),
                type(payload[key]),
                msg=f'{parent_path}: key {key} type does not match'
            )
            if key in ['stac_extensions', 'spatial', 'temporal', 'created', 'updated']:
                # remove this if when all parts are fully implemented.
                # See BGDIINF_SB-1410, BGDIINF_SB-1427 and BGDIINF_SB-1429
                logger.warning('%s: Ignore key %s check', parent_path, key)
                continue
            if isinstance(value, dict):
                self._test_dict(path, value, payload[key])
            elif isinstance(value, list):
                if key in ['geoadmin:variant']:
                    self._test_list(path, sorted(value), sorted(payload[key]))
                else:
                    self._test_list(path, value, payload[key])
            else:
                self.assertEqual(
                    value, payload[key], msg=f'{parent_path}: Key {key} is not equal in payload'
                )

    def _test_list(self, parent_path, lst, payload):
        for i, value in enumerate(lst):
            path = f'{parent_path}[{i}]'
            if isinstance(value, dict):
                self._test_dict(path, value, payload[i])
            elif isinstance(value, list):
                self._test_list(path, value, payload[i])
            else:
                self.assertEqual(
                    value, payload[i], msg=f'{parent_path}: List index {i} is not equal in payload'
                )
