import json
import logging
import os
from pathlib import Path

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
        self.assertEqual(200, response.status_code)

        self._test_dict(collection_dict, payload)

    def _test_dict(self, dct, payload):
        for key, value in dct.items():
            self.assertIn(key, payload, msg=f'Key {key} is not in payload')
            if isinstance(value, dict):
                self._test_dict(value, payload[key])
            elif isinstance(value, list):
                pass
            elif key == 'stac_extensions':
                pass
            else:
                self.assertEqual(str(value), payload[key], msg=f'Key {key} is not equal in payload')
