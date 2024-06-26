from django.urls import include
from django.urls import path
from django.urls import re_path

from rest_framework.authtoken.views import obtain_auth_token

from stac_api.views import AssetDetail
from stac_api.views import AssetsList
from stac_api.views import AssetUploadAbort
from stac_api.views import AssetUploadComplete
from stac_api.views import AssetUploadDetail
from stac_api.views import AssetUploadPartsList
from stac_api.views import AssetUploadsList
from stac_api.views import CollectionDetail
from stac_api.views import CollectionList
from stac_api.views import ConformancePageDetail
from stac_api.views import ItemDetail
from stac_api.views import ItemsList
from stac_api.views import LandingPageDetail
from stac_api.views import SearchList

# HEALTHCHECK_ENDPOINT = settings.HEALTHCHECK_ENDPOINT

asset_upload_urls = [
    path("<upload_id>", AssetUploadDetail.as_view(), name='asset-upload-detail'),
    path("<upload_id>/parts", AssetUploadPartsList.as_view(), name='asset-upload-parts-list'),
    path("<upload_id>/complete", AssetUploadComplete.as_view(), name='asset-upload-complete'),
    path("<upload_id>/abort", AssetUploadAbort.as_view(), name='asset-upload-abort')
]

asset_urls = [
    path("<asset_name>", AssetDetail.as_view(), name='asset-detail'),
    path("<asset_name>/uploads", AssetUploadsList.as_view(), name='asset-uploads-list'),
    path("<asset_name>/uploads/", include(asset_upload_urls))
]

item_urls = [
    path("<item_name>", ItemDetail.as_view(), name='item-detail'),
    path("<item_name>/assets", AssetsList.as_view(), name='assets-list'),
    path("<item_name>/assets/", include(asset_urls))
]

collection_urls = [
    path("<collection_name>", CollectionDetail.as_view(), name='collection-detail'),
    path("<collection_name>/items", ItemsList.as_view(), name='items-list'),
    path("<collection_name>/items/", include(item_urls))
]

urlpatterns = [
    # Deactivate healthcheck for now while monitoring is being adapted.
    # path(f"{HEALTHCHECK_ENDPOINT}", CollectionList.as_view(), name='health-check'),
    path("get-token", obtain_auth_token, name='get-token'),
    re_path(
        "^v0.9/",
        include(([
            path("", LandingPageDetail.as_view(), name='landing-page'),
            path("conformance", ConformancePageDetail.as_view(), name='conformance'),
            path("search", SearchList.as_view(), name='search-list'),
            path("collections", CollectionList.as_view(), name='collections-list'),
            path("collections/", include(collection_urls))
        ],
                 "v0.9"),
                namespace='v0.9')
    ),
    re_path(
        "^v1/",
        include(([
            path("", LandingPageDetail.as_view(), name='landing-page'),
            path("conformance", ConformancePageDetail.as_view(), name='conformance'),
            path("search", SearchList.as_view(), name='search-list'),
            path("collections", CollectionList.as_view(), name='collections-list'),
            path("collections/", include(collection_urls))
        ],
                 "v1"),
                namespace='v1')
    )
]
