import glob
import json
import logging
import os
from pathlib import Path
from pprint import pformat
from unittest import skip

from django.conf import settings
from django.test import Client

from stac_api.sample_data import importer

from tests.tests_10.base_test import STAC_BASE_V
from tests.tests_10.base_test import StacBaseTestCase
from tests.utils import MockS3PerClassMixin
from tests.utils import get_http_error_description

logger = logging.getLogger(__name__)

DATADIR = settings.BASE_DIR / 'app/stac_api/sample_data/'


class SampleDataTestCase(MockS3PerClassMixin, StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()

        self.maxDiff = None  # pylint: disable=invalid-name

    @skip("Broken for a long time, see PB-1740")
    def test_samples(self):
        for collection_dir in os.scandir(DATADIR):
            if collection_dir.is_dir() and not collection_dir.name.startswith('_'):
                with self.subTest(
                    msg=f'test sample {collection_dir.name}', collection_dir=collection_dir
                ):
                    self._test_collection(Path(collection_dir.path))

    def _test_collection(self, collection_dir):
        collection = importer.import_collection(collection_dir)

        with open(collection_dir / 'collection.json', encoding="utf-8") as fd:
            collection_dict = json.load(fd)

        response = self.client.get(f"/{STAC_BASE_V}/collections/{collection.name}")
        payload = response.json()
        logger.debug('Collection %s payload:\n%s', collection.name, pformat(payload))
        self.assertEqual(200, response.status_code, msg=get_http_error_description(payload))

        # we ignore the created and updated attribute because they cannot match the one from the
        # samples as they are automatically generated with the time of creation/update
        self.check_stac_collection(collection_dict, payload, ignore=['created', 'updated', 'href'])

        for item_file in glob.iglob(str(collection_dir / 'items' / '*.json')):
            with self.subTest(
                msg=f'test sample {collection_dir.name}/{os.path.basename(item_file)}',
                item_file=item_file,
                collection_name=collection.name
            ):
                self._test_item(collection.name, item_file)

    def _test_item(self, collection_name, item_file):
        with open(item_file, encoding="utf-8") as fd:
            item_dict = json.load(fd)

        response = self.client.get(
            f"/{STAC_BASE_V}/collections/{collection_name}/items/{item_dict['id']}"
        )
        payload = response.json()
        logger.debug('Item %s.%s payload:\n%s', collection_name, item_dict['id'], pformat(payload))
        self.assertEqual(200, response.status_code, msg=get_http_error_description(payload))

        # we ignore the created and updated attribute because they cannot match the one from the
        # samples as they are automatically generated with the time of creation/update.
        self.check_stac_item(item_dict, payload, collection_name, ignore=['created', 'updated'])
