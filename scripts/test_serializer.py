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

link_root = CollectionLink.objects.create(
            item=self.item,
            href="https://data.geo.admin.ch/api/stac/v0.9/",
            rel='root',
            link_type='root',
            title='Root link'
        )



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
    description='test',
    extent={
    "spatial": {
      "bbox": [
        [
		  5.685114,
		  45.534903,
		  10.747775,
		  47.982586
        ]
      ]
    },
    "temporal": {
      "interval": [
        [
          "2019",
          None
        ]
      ]
    }
  },
    collection_name='my collection',
    item_type='Feature',
    license='test',
    stac_extension=get_default_stac_extensions(),
    stac_version="0.9.0",
    summaries = {
    "eo:gsd": [10,20],
    "geoadmin:variant": ["kgrel", "komb", "krel"],
    "proj:epsg": [2056]
  },
    title='testtitel2'
)

collection1.save()

# populate the ManyToMany relation fields
collection1.links.add(link_root)
collection1.keywords.add(keyword1, keyword3)
collection1.providers.add(provider1, provider2)
collection1.save()

# create collection instance for testing
collection2 = Collection(
    id=2,
    crs=['http://www.google.com'],
    created=datetime.now(),
    updated=datetime.now(),
    description='test',
    extent={
    "spatial": {
      "bbox": [
        [
		  5.685114,
		  45.534903,
		  10.747775,
		  47.982586
        ]
      ]
    },
    "temporal": {
      "interval": [
        [
          "2019",
          None
        ]
      ]
    }
  },
    collection_name='b_123',
    item_type='Feature',
    license='test',
    stac_extension=get_default_stac_extensions(),
    stac_version="0.9.0",
    summaries = {
    "eo:gsd": [10,20],
    "geoadmin:variant": ["kgrel", "komb", "krel"],
    "proj:epsg": [2056]
  },
    title='testtitel2'
)
collection2.save()
# populate the ManyToMany relation fields
collection2.links.add(link_root)
collection2.keywords.add(keyword2, keyword3)
collection2.providers.add(provider1, provider3)

# create collection instance for testing
collection3 = Collection(
    id=3,
    crs=['http://www.google.com'],
    created=datetime.now(),
    updated=datetime.now(),
    description='test',
    extent={
    "spatial": {
      "bbox": [
        [
		  5.685114,
		  45.534903,
		  10.747775,
		  47.982586
        ]
      ]
    },
    "temporal": {
      "interval": [
        [
          "2019",
          None
        ]
      ]
    }
  },
    collection_name='c_123',
    item_type='Feature',
    license='test',
    stac_extension=get_default_stac_extensions(),
    stac_version="0.9.0",
    summaries = {
    "eo:gsd": [10,20],
    "geoadmin:variant": ["kgrel", "komb", "krel"],
    "proj:epsg": [2056]
  },
    title='testtitel2'
)
collection3.save()
# populate the ManyToMany relation fields
collection3.links.add(link_root)
collection3.keywords.add(keyword2, keyword3)
collection3.providers.add(provider1, provider3)
collection3.save()

keyword1.save()
keyword2.save()
keyword3.save()
provider1.save()
provider2.save()
provider3.save()
link_root.save()


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
