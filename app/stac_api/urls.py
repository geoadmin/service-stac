from django.conf import settings
from django.urls import path

from stac_api.views import AssetDetail
from stac_api.views import AssetsList
from stac_api.views import CollectionDetail
from stac_api.views import CollectionList
from stac_api.views import ConformancePageDetail
from stac_api.views import ItemDetail
from stac_api.views import ItemsList
from stac_api.views import LandingPageDetail

from . import views

API_BASE = settings.API_BASE

urlpatterns = [
    path(f'{API_BASE}/', LandingPageDetail.as_view(), name='landing-page'),
    path(f'{API_BASE}/conformance', ConformancePageDetail.as_view(), name='conformance'),
    path('checker/', views.checker, name='checker'),
    path(f"{API_BASE}/collections", CollectionList.as_view(), name='collection-list'),
    path(
        f"{API_BASE}/collections/<collection_name>",
        CollectionDetail.as_view(),
        name='collection-detail'
    ),
    path(f"{API_BASE}/collections/<collection_name>/items", ItemsList.as_view(), name='items-list'),
    path(
        f"{API_BASE}/collections/<collection_name>/items/<item_name>",
        ItemDetail.as_view(),
        name='item-detail'
    ),
    path(
        f"{API_BASE}/collections/<collection_name>/items/<item_name>/assets",
        AssetsList.as_view(),
        name='assets-list'
    ),
    path(
        f"{API_BASE}/collections/<collection_name>/items/<item_name>/assets/<asset_name>",
        AssetDetail.as_view(),
        name='asset-detail'
    ),
]
