import json
import logging
import os
import glob
from pathlib import Path
from pprint import pformat

from django.conf import settings
from django.test import Client

from stac_api.sample_data import importer

from tests.utils import get_http_error_description
from tests.base_test import StacBaseTestCase

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE
DATADIR = settings.BASE_DIR / 'app/stac_api/sample_data/'


class SampleDataTestCase(StacBaseTestCase):

    def setUp(self):
        self.client = Client()

        self.maxDiff = None  # pylint: disable=invalid-name

    def test_samples(self):
        for collection_dir in os.scandir(DATADIR):
            if collection_dir.is_dir() and not collection_dir.name.startswith('_'):
                with self.subTest(
                    msg=f'test sample {collection_dir.name}', collection_dir=collection_dir
                ):
                    self._test_collection(Path(collection_dir.path))

    def _test_collection(self, collection_dir):
        collection = importer.import_collection(collection_dir)

        with open(collection_dir / 'collection.json') as fd:
            collection_dict = json.load(fd)

        response = self.client.get(f"/{API_BASE}collections/{collection.collection_name}")
        payload = response.json()
        logger.debug('Collection %s payload:\n%s', collection.collection_name, pformat(payload))
        self.assertEqual(200, response.status_code, msg=get_http_error_description(payload))

        # we ignore the created and updated attribute because they cannot match the one from the
        # samples as they are automatically generated with the time of creation/update
        self.check_stac_collection(collection_dict, payload, ignore=['created', 'updated'])

        for item_file in glob.iglob(str(collection_dir / 'items' / '*.json')):
            with self.subTest(
                msg=f'test sample {collection_dir.name}/{os.path.basename(item_file)}',
                item_file=item_file,
                collection_name=collection.collection_name
            ):
                self._test_item(collection.collection_name, item_file)

    def _test_item(self, collection_name, item_file):
        with open(item_file) as fd:
            item_dict = json.load(fd)

        response = self.client.get(
            f"/{API_BASE}collections/{collection_name}/items/{item_dict['id']}"
        )
        payload = response.json()
        logger.debug('Item %s.%s payload:\n%s', collection_name, item_dict['id'], pformat(payload))
        self.assertEqual(200, response.status_code, msg=get_http_error_description(payload))

        # we ignore the created and updated attribute because they cannot match the one from the
        # samples as they are automatically generated with the time of creation/update
        # remove "eo:bands" from ignore once BGDIINF_SB-1435 is implemented
        self.check_stac_item(item_dict, payload, ignore=['created', 'updated', 'eo:bands'])
