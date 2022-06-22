from django.urls import path

from stac_api.views import ConformancePageDetail
from stac_api.views import SearchList

from stac_api_v1.views import V1CollectionList
from stac_api_v1.views import V1LandingPageDetail

app_name = 'stac_api'

urlpatterns = [
    path("", V1LandingPageDetail.as_view(), name='landing-page'),
    path("conformance", ConformancePageDetail.as_view(), name='conformance'),
    path("search", SearchList.as_view(), name='search-list'),
    path("collections", V1CollectionList.as_view(), name='collections-list'),
]
