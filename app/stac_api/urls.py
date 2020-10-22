from django.urls import path

from config.settings import API_BASE_PATH
from stac_api.views import CollectionDetail
from stac_api.views import CollectionList

from . import views

urlpatterns = [
    path(API_BASE_PATH, views.landing_page, name='landing-page'),
    path('checker/', views.checker, name='checker'),
    path(f"{API_BASE_PATH}collections/", CollectionList.as_view(), name='collection-list'),
    path(
        f"{API_BASE_PATH}collections/<slug:collection_name>/",
        CollectionDetail.as_view(),
        name='collection-detail'
    ),
]
