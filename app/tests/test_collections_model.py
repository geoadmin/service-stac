import logging

from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase

from stac_api.models import Collection

logger = logging.getLogger(__name__)


class CollectionsModelTestCase(TestCase):

    def test_collection_create_model(self):
        collection = Collection(
            name='collection-1',
            extent_geometry=GEOSGeometry(
                'SRID=4326;POLYGON '
                '((5.96 45.82, 5.96 47.81, 10.49 47.81, 10.49 45.82, 5.96 45.82))'
            ),
            description='cool collection',
            license='WTFPL'
        )
        collection.full_clean()
        collection.save()
        self.assertEqual('collection-1', collection.name)
