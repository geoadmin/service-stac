import json
import logging
from pprint import pformat
from unittest import skip
from difflib import ndiff
from django.conf import settings
from django.test import Client
from django.test import TestCase

from rest_framework.renderers import JSONRenderer


from stac_api.sample_data import importer

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE
DATADIR = settings.BASE_DIR / 'app/stac_api/sample_data/'


class SampleDataTestCase(TestCase):

    def setUp(self):
        self.client = Client()

        self.collection = importer.import_collection(DATADIR / 'swissTLM3D/')
        with open(DATADIR / 'swissTLM3D/collection.json') as f:
            self.collection_dict = json.load(f)
    

        self.maxDiff = None  # pylint: disable=invalid-name

    @skip
    def test_print_diff(self):

        
        response = self.client.get(f"/{API_BASE}collections/{self.collection.collection_name}")
        payload = response.json()
        # print(payload)
        # diff = {k: payload[k] for k, _ in set(
        #     payload.items()) - set(self.collection_dict.items())}
        # dict_compare(self.collection_dict, payload)
        
        logger.debug('- input json, + payload')
        self.assertDictEqual(self.collection_dict, payload)
        # print(diff)
