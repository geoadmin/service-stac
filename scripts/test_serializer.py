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

# create keyword instance for testing
keyword = Keyword(name='test1')
keyword.save()

# create link instance for testing
link = Link(href='http://www.google.com', rel='rel', link_type='root', title='testtitel')
link.save()

# create provider instance for testing
provider = Provider(
    name='provider1', description='descr', roles=['licensor'], url='http://www.google.com'
)
provider.save()

# create collection instance for testing
collection = Collection(
    id=1,
    crs=['http://www.google.com'],
    created=datetime.now(),
    updated=datetime.now(),
    description='desc',
    start_date=None,
    end_date=None,
    extent=[],
    collection_name='collectionname',
    item_type='Feature',
    license='test',
    stac_extension=get_default_stac_extensions(),
    stac_version="0.9.0",
    summaries_eo_gsd=None,
    summaries_proj=None,
    geoadmin_variant=None,
    title='testtitel'
)
collection.save()

# populate the ManyToMany relation fields
collection.links.add(link)
collection.keywords.add(keyword)
collection.providers.add(provider)

collection.save()
keyword.save()
provider.save()
link.save()

# test the serialization process:
# translate into Python native
serializer = CollectionSerializer(collection)
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