from stac_api.views import CollectionList
from stac_api.views import LandingPageDetail

from stac_api_v1.serializer import V1CollectionSerializer
from stac_api_v1.serializer import V1LandingPageSerializer

# Create your views here.


class V1LandingPageDetail(LandingPageDetail):
    name = 'landing-page'  # this name must match the name in urls.py
    serializer_class = V1LandingPageSerializer


class V1CollectionList(CollectionList):
    name = 'collections-list'  # this name must match the name in urls.py
    serializer_class = V1CollectionSerializer
