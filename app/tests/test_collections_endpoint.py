from django.conf import settings
from django.test import Client
from django.test import TestCase

from stac_api.serializers import CollectionSerializer

import tests.database as db

API_BASE = settings.API_BASE


class CollectionsEndpointTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.collection = db.create_collection()
        # create keyword instances for testing
        self.keyword1 = Keyword.objects.create(name='test1')
        self.keyword1.save()

        self.keyword2 = Keyword.objects.create(name='test2')
        self.keyword2.save()

        self.keyword3 = Keyword.objects.create(name='test3')
        self.keyword3.save()

        # create provider instances for testing
        self.provider1 = Provider.objects.create(
            name='provider1',
            description='description1',
            roles=['licensor'],
            url='http://www.google.com'
        )
        self.provider1.save()

        self.provider2 = Provider.objects.create(
            name='provider2',
            description='description2',
            roles=['licensor'],
            url='http://www.google.com'
        )
        self.provider2.save()

        self.provider3 = Provider.objects.create(
            name='provider3',
            description='description3',
            roles=['licensor'],
            url='http://www.google.com'
        )
        self.provider3.save()

        # create collection instances for testing
        self.collection1 = Collection.objects.create(
            id=1,
            crs=['http://www.google.com'],
            created=datetime.now(),
            updated=datetime.now(),
            description='description lalala tralalla',
            extent={
                "spatial": {
                    "bbox": [[None]]
                }, "temporal": {
                    "interval": [[None, None]]
                }
            },
            collection_name='a_123',
            item_type='Feature',
            license='test',
            stac_extension=get_default_stac_extensions(),
            stac_version="0.9.0",
            summaries={
                "eo:gsd": None, "geoadmin:variant": None, "proj:epsg": None
            },
            title='testtitel'
        )
        self.collection1.save()

        # populate the ManyToMany relation fields
        self.collection1.keywords.add(self.keyword1, self.keyword3)
        self.collection1.providers.add(self.provider1, self.provider2)
        self.collection1.save()

        # create collection instance for testing
        self.collection2 = Collection.objects.create(
            id=2,
            crs=['http://www.google.com'],
            created=datetime.now(),
            updated=datetime.now(),
            description='',
            extent={
                "spatial": {
                    "bbox": [[5.685114, 45.534903, 10.747775, 47.982586]]
                },
                "temporal": {
                    "interval": [["2019", None]]
                }
            },
            collection_name='b_123',
            item_type='Feature',
            license='test',
            stac_extension=get_default_stac_extensions(),
            stac_version="0.9.0",
            summaries={
                "eo:gsd": [10, 20],
                "geoadmin:variant": ["kgrel", "komb", "krel"],
                "proj:epsg": [2056]
            },
            title='testtitel2'
        )
        self.collection2.save()
        # populate the ManyToMany relation fields
        self.collection2.keywords.add(self.keyword2, self.keyword3)
        self.collection2.providers.add(self.provider1, self.provider3)

        # create collection instance for testing
        self.collection3 = Collection.objects.create(
            id=3,
            crs=['http://www.google.com'],
            created=datetime.now(),
            updated=datetime.now(),
            description='description3 bla bla blubb',
            extent={
                "spatial": {
                    "bbox": [[None]]
                }, "temporal": {
                    "interval": [[None, None]]
                }
            },
            collection_name='c_123',
            item_type='Feature',
            license='test',
            stac_extension=get_default_stac_extensions(),
            stac_version="0.9.0",
            summaries={
                "eo:gsd": None, "geoadmin:variant": None, "proj:epsg": None
            },
            title='testtitel3'
        )
        self.collection3.save()
        # populate the ManyToMany relation fields
        self.collection3.keywords.add(self.keyword2, self.keyword3)
        self.collection3.providers.add(self.provider1, self.provider3)
        self.collection3.save()

        self.keyword1.save()
        self.keyword2.save()
        self.keyword3.save()
        self.provider1.save()
        self.provider2.save()
        self.provider3.save()

        # create link instances for testing
        self.link1 = CollectionLink.objects.create(
            collection=self.collection1,
            href='/collections/a_123/?format=json',
            rel='self',
            link_type='image/png',
            title='test title'
        )
        self.link1.save()

        self.link2 = CollectionLink.objects.create(
            collection=self.collection2,
            href='/collections/b_123/?format=json',
            rel='self',
            link_type='image/png',
            title='test title 2'
        )
        self.link2.save()

        self.link3 = CollectionLink.objects.create(
            collection=self.collection3,
            href='/collections/c_123/?format=json',
            rel='self',
            link_type='image/png',
            title='test title 3'
        )
        self.link3.save()

        # transate to Python native:
        self.serializer = CollectionSerializer(self.collection)

    def test_collections_endpoint(self):
        collection_name = self.collection.collection_name
        response = self.client.get(f"/{API_BASE}collections?format=json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['collections'][0],
            self.serializer.data,
            msg="Returned data does not match expected data"
        )

    def test_single_collection_endpoint(self):
        collection_name = self.collection.collection_name
        response = self.client.get(f"/{API_BASE}collections/{collection_name}?format=json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data, self.serializer.data, msg="Returned data does not match expected data"
        )
