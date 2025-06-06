from django.urls import include
from django.urls import path
from django.urls import re_path

from rest_framework.authtoken.views import obtain_auth_token

from stac_api.views.collection import CollectionAssetDetail
from stac_api.views.collection import CollectionAssetsList
from stac_api.views.collection import CollectionDetail
from stac_api.views.collection import CollectionList
from stac_api.views.general import ConformancePageDetail
from stac_api.views.general import LandingPageDetail
from stac_api.views.general import SearchList
from stac_api.views.general import recalculate_extent
from stac_api.views.item import AssetDetail
from stac_api.views.item import AssetsList
from stac_api.views.item import ItemDetail
from stac_api.views.item import ItemsList
from stac_api.views.upload import AssetUploadAbort
from stac_api.views.upload import AssetUploadComplete
from stac_api.views.upload import AssetUploadDetail
from stac_api.views.upload import AssetUploadPartsList
from stac_api.views.upload import AssetUploadsList
from stac_api.views.upload import CollectionAssetUploadAbort
from stac_api.views.upload import CollectionAssetUploadComplete
from stac_api.views.upload import CollectionAssetUploadDetail
from stac_api.views.upload import CollectionAssetUploadPartsList
from stac_api.views.upload import CollectionAssetUploadsList

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

collection_asset_upload_urls = [
    path(
        "<upload_id>", CollectionAssetUploadDetail.as_view(), name='collection-asset-upload-detail'
    ),
    path(
        "<upload_id>/parts",
        CollectionAssetUploadPartsList.as_view(),
        name='collection-asset-upload-parts-list'
    ),
    path(
        "<upload_id>/complete",
        CollectionAssetUploadComplete.as_view(),
        name='collection-asset-upload-complete'
    ),
    path(
        "<upload_id>/abort",
        CollectionAssetUploadAbort.as_view(),
        name='collection-asset-upload-abort'
    ),
]

collection_asset_urls = [
    path("<asset_name>", CollectionAssetDetail.as_view(), name='collection-asset-detail'),
    path(
        "<asset_name>/uploads",
        CollectionAssetUploadsList.as_view(),
        name='collection-asset-uploads-list'
    ),
    path("<asset_name>/uploads/", include(collection_asset_upload_urls))
]

collection_urls = [
    path("<collection_name>", CollectionDetail.as_view(), name='collection-detail'),
    path("<collection_name>/items", ItemsList.as_view(), name='items-list'),
    path("<collection_name>/items/", include(item_urls)),
    path("<collection_name>/assets", CollectionAssetsList.as_view(), name='collection-assets-list'),
    path("<collection_name>/assets/", include(collection_asset_urls))
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
            path("collections/", include(collection_urls)),
            path("update-extent", recalculate_extent)
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
            path("collections/", include(collection_urls)),
            path("update-extent", recalculate_extent)
        ],
                 "v1"),
                namespace='v1')
    )
]
