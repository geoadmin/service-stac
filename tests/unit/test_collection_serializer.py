import io
from datetime import datetime

from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer

from django.test import TestCase

from stac_api.models import Collection
from stac_api.models import Keyword
from stac_api.models import Link
from stac_api.models import Provider
from stac_api.models import get_default_stac_extensions
from stac_api.serializers import CollectionSerializer


class SerializationTestCase(TestCase):

    def setUp(self):
        '''
        Prepare instances of keyword, link, provider and instance for testing.
        Adding the relationships among those by populating the ManyToMany fields
        '''
        # create keyword instance for testing
        self.keyword = Keyword.objects.create(name='test1')
        self.keyword.save()

        # create link instance for testing
        self.link = Link.objects.create(
            href='http://www.google.com', rel='rel', link_type='root', title='Test title'
        )
        self.link.save()

        # create provider instance for testing
        self.provider = Provider.objects.create(
            name='provider1', description='descr', roles=['licensor'], url='http://www.google.com'
        )
        self.provider.save()

        # create collection instance for testing
        self.collection = Collection.objects.create(
            id=1,
            crs=['http://www.google.com'],
            created=datetime.now(),
            updated=datetime.now(),
            description='desc',
            start_date=None,
            end_date=None,
            southwest=[20, 20, 20],
            northeast=[10, 10, 10],
            collection_name='collectionname',
            item_type='Feature',
            license='test',
            stac_extension=get_default_stac_extensions(),
            stac_version="0.9.0",
            summaries_eo_gsd=[10.1, 20.3, 30.44],
            summaries_proj=[1, 4, 22],
            geoadmin_variant=['blubb', 'blabb', 'blibb'],
            title='Test title'
        )
        self.collection.save()

        # populate the ManyToMany relation fields
        self.collection.links.add(self.link)
        self.collection.keywords.add(self.keyword)
        self.collection.providers.add(self.provider)

        # save the updated instances
        self.collection.save()
        self.keyword.save()
        self.provider.save()
        self.link.save()

    def test_serialization(self):

        # transate to Python native:
        serializer = CollectionSerializer(self.collection)
        python_native = serializer.data

        # translate to JSON:
        content = JSONRenderer().render(python_native)

        # back-transate to Python native:
        stream = io.BytesIO(content)
        data = JSONParser().parse(stream)

        # back-translate into fully populated collection instance:
        serializer = CollectionSerializer(data=data)

        self.assertEqual(serializer.is_valid(), True, msg='Serializer data not valid.')
        self.assertEqual(python_native, data, msg='Back-translated data not equal initial data.')
