from django.conf import settings
from django.urls import path

from stac_api.views import CollectionDetail
from stac_api.views import CollectionList
from stac_api.views import ItemDetail
from stac_api.views import ItemsList

from . import views

API_BASE = settings.API_BASE

urlpatterns = [
    path(API_BASE, views.landing_page, name='landing-page'),
    path('checker/', views.checker, name='checker'),
    path(f"{API_BASE}collections", CollectionList.as_view(), name='collection-list'),
    path(
        f"{API_BASE}collections/<str:collection_name>",
        CollectionDetail.as_view(),
        name='collection-detail'
    ),
    path(
        f"{API_BASE}collections/<str:collection_name>/items",
        ItemsList.as_view(),
        name='items-list'
    ),
    path(
        f"{API_BASE}collections/<str:collection_name>/items/<str:item_name>",
        ItemDetail.as_view(),
        name='item-detail'
    ),
]
