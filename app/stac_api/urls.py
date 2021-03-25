from django.conf import settings
from django.urls import path

from rest_framework.authtoken.views import obtain_auth_token

from stac_api.views import AssetDetail
from stac_api.views import AssetsList
from stac_api.views import CollectionDetail
from stac_api.views import CollectionList
from stac_api.views import ConformancePageDetail
from stac_api.views import ItemDetail
from stac_api.views import ItemsList
from stac_api.views import LandingPageDetail
from stac_api.views import SearchList

STAC_VERSION_SHORT = settings.STAC_VERSION_SHORT
HEALTHCHECK_ENDPOINT = settings.HEALTHCHECK_ENDPOINT

urlpatterns = [
    path(f"{HEALTHCHECK_ENDPOINT}", CollectionList.as_view(), name='health-check'),
    path("get-token", obtain_auth_token, name='get-token'),
    path(f"{STAC_VERSION_SHORT}/", LandingPageDetail.as_view(), name='landing-page'),
    path(f"{STAC_VERSION_SHORT}/conformance", ConformancePageDetail.as_view(), name='conformance'),
    path(f"{STAC_VERSION_SHORT}/search", SearchList.as_view(), name='search-list'),
    path(f"{STAC_VERSION_SHORT}/collections", CollectionList.as_view(), name='collections-list'),
    path(
        f"{STAC_VERSION_SHORT}/collections/<collection_name>",
        CollectionDetail.as_view(),
        name='collection-detail'
    ),
    path(
        f"{STAC_VERSION_SHORT}/collections/<collection_name>/items",
        ItemsList.as_view(),
        name='items-list'
    ),
    path(
        f"{STAC_VERSION_SHORT}/collections/<collection_name>/items/<item_name>",
        ItemDetail.as_view(),
        name='item-detail'
    ),
    path(
        f"{STAC_VERSION_SHORT}/collections/<collection_name>/items/<item_name>/assets",
        AssetsList.as_view(),
        name='assets-list'
    ),
    path(
        f"{STAC_VERSION_SHORT}/collections/<collection_name>/items/<item_name>/assets/<asset_name>",
        AssetDetail.as_view(),
        name='asset-detail'
    )
]
