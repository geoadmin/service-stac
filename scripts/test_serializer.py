# This is a little script that I used for locally testing the serializer for
# collections.
# also see: https://www.django-rest-framework.org/tutorial/1-serialization/
#
#
# probably flush your local table first, to start from scratch:
# in the /app/ diretory ./manage.py flush

# run this script like so:
# 1. ./manage.py shell (inside the app dir)
# 2. exec(open('../scripts/test_serializer.py').read())
# after running this script, you can have a look at:
# - serializer.data (Python natives)
# - content (JSON)
# - data (back-translated into Python native)
# - serializer.validated_data # back-translated into fully populated collection instance

from datetime import datetime
import io
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import JSONParser
from stac_api.models import *
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import KeywordSerializer
from stac_api.serializers import LinkSerializer
from stac_api.serializers import ProviderSerializer

# create keyword instances for testing
keyword1 = Keyword(name='test1')
keyword1.save()

keyword2 = Keyword(name='test2')
keyword2.save()

keyword3 = Keyword(name='test3')
keyword3.save()

# create link instances for testing
link1 = Link.objects.create(
    href='/collections/a_123/?format=json', rel='self', link_type='image/png', title='testtitel'
)
link1.save()

link2 = Link.objects.create(
    href='/collections/b_123/', rel='self', link_type='image/png', title='testtitel2'
)
link2.save()

link3 = Link.objects.create(
    href='/collections/c_123/?format=json', rel='self', link_type='image/png', title='testtitel3'
)
link3.save()

# create provider instances for testing
provider1 = Provider(
    name='provider1', description='description1', roles=['licensor'], url='http://www.google.com'
)
provider1.save()

provider2 = Provider(
    name='provider2', description='description2', roles=['licensor'], url='http://www.google.com'
)
provider2.save()

provider3 = Provider(
    name='provider3', description='description3', roles=['licensor'], url='http://www.google.com'
)
provider3.save()

# create collection instances for testing
collection1 = Collection(
    id=1,
    crs=['http://www.google.com'],
    created=datetime.now(),
    updated=datetime.now(),
    description='description lalala tralalla',
    start_date=None,
    end_date=None,
    southwest=[20, 20, 20],
    northeast=[10, 10, 10],
    collection_name='a_123',
    item_type='Feature',
    license='test',
    stac_extension=get_default_stac_extensions(),
    stac_version="0.9.0",
    summaries_eo_gsd=[10.1, 20.3, 30.44],
    summaries_proj=[1, 4, 22],
    geoadmin_variant=['blubb', 'blabb', 'blibb'],
    title='testtitel'
)
collection1.save()

# populate the ManyToMany relation fields
collection1.links.add(link1)
collection1.keywords.add(keyword1, keyword3)
collection1.providers.add(provider1, provider2)
collection1.save()

# create collection instance for testing
collection2 = Collection(
    id=2,
    crs=['http://www.google.com'],
    created=datetime.now(),
    updated=datetime.now(),
    description='',
    start_date=None,
    end_date=None,
    southwest=[20, 20, 20],
    northeast=[10, 10, 10],
    collection_name='b_123',
    item_type='Feature',
    license='test',
    stac_extension=get_default_stac_extensions(),
    stac_version="0.9.0",
    summaries_eo_gsd=[10.1, 20.3, 30.44],
    summaries_proj=[1, 4, 22],
    geoadmin_variant=['blubb', 'blabb', 'blibb'],
    title='testtitel2'
)
collection2.save()
# populate the ManyToMany relation fields
collection2.links.add(link2)
collection2.keywords.add(keyword2, keyword3)
collection2.providers.add(provider1, provider3)

# create collection instance for testing
collection3 = Collection(
    id=3,
    crs=['http://www.google.com'],
    created=datetime.now(),
    updated=datetime.now(),
    description='description3 bla bla blubb',
    start_date=None,
    end_date=None,
    southwest=[20, 20, 20],
    northeast=[10, 10, 10],
    collection_name='c_123',
    item_type='Feature',
    license='test',
    stac_extension=get_default_stac_extensions(),
    stac_version="0.9.0",
    summaries_eo_gsd=[10.1, 20.3, 30.44],
    summaries_proj=[1, 4, 22],
    geoadmin_variant=['blubb', 'blabb', 'blibb'],
    title='testtitel3'
)
collection3.save()
# populate the ManyToMany relation fields
collection3.links.add(link3)
collection3.keywords.add(keyword2, keyword3)
collection3.providers.add(provider1, provider3)
collection3.save()

keyword1.save()
keyword2.save()
keyword3.save()
provider1.save()
provider2.save()
provider3.save()
link1.save()
link2.save()
link3.save()

# test the serialization process:
# translate into Python native
serializer = CollectionSerializer(collection1)
serializer.data

# translate into json
content = JSONRenderer().render(serializer.data)
content

# back-translate into Python native
stream = io.BytesIO(content)
data = JSONParser().parse(stream)

# back-translate into fully populated object instance
serializer = CollectionSerializer(data=data)
serializer.is_valid()  # hopefully True, if False, serializer.errors gives hints

serializer.validated_data
