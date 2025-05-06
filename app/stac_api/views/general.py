import json
import logging
from datetime import datetime

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rest_framework import generics
from rest_framework import mixins
from rest_framework import permissions
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from stac_api.models.general import LandingPage
from stac_api.models.item import Item
from stac_api.pagination import GetPostCursorPagination
from stac_api.serializers.general import ConformancePageSerializer
from stac_api.serializers.general import LandingPageSerializer
from stac_api.serializers.item import ItemSerializer
from stac_api.serializers.utils import get_relation_links
from stac_api.utils import call_calculate_extent
from stac_api.utils import harmonize_post_get_for_search
from stac_api.utils import is_api_version_1
from stac_api.utils import utc_aware
from stac_api.validators_serializer import ValidateSearchRequest
from stac_api.views.mixins import patch_collections_aggregate_cache_control_header

logger = logging.getLogger(__name__)


def get_etag(queryset):
    if queryset.exists():
        return list(queryset.only('etag').values('etag').first().values())[0]
    return None


class LandingPageDetail(generics.RetrieveAPIView):
    name = 'landing-page'  # this name must match the name in urls.py
    serializer_class = LandingPageSerializer
    queryset = LandingPage.objects.all()

    def get_object(self):
        if not is_api_version_1(self.request):
            return LandingPage.objects.get(version='v0.9')
        return LandingPage.objects.get(version='v1')


class ConformancePageDetail(generics.RetrieveAPIView):
    name = 'conformance'  # this name must match the name in urls.py
    serializer_class = ConformancePageSerializer
    queryset = LandingPage.objects.all()

    def get_object(self):
        if not is_api_version_1(self.request):
            return LandingPage.objects.get(version='v0.9')
        return LandingPage.objects.get(version='v1')


class SearchList(generics.GenericAPIView, mixins.ListModelMixin):
    name = 'search-list'  # this name must match the name in urls.py
    permission_classes = [AllowAny]
    serializer_class = ItemSerializer
    pagination_class = GetPostCursorPagination
    # It is important to order the result by a unique identifier, because the search endpoint
    # search overall collections and that the item name is only unique within a collection
    # we must use the pk as ordering attribute, otherwise the cursor pagination will not work
    ordering = ['pk']

    # pylint: disable=too-many-branches
    def get_queryset(self):
        filter_condition = Q(collection__published=True)
        if settings.FEATURE_HIDE_EXPIRED_ITEMS_IN_SEARCH_ENABLED:
            is_active = Q(properties_expires=None) | Q(properties_expires__gte=timezone.now())
            filter_condition &= is_active
        queryset = Item.objects.filter(filter_condition).prefetch_related('assets', 'links')

        # harmonize GET and POST query
        query_param = harmonize_post_get_for_search(self.request)

        # build queryset

        # if ids, then the other params will be ignored
        if 'ids' in query_param:
            queryset = queryset.filter_by_item_name(query_param['ids'])
        else:
            if 'bbox' in query_param:
                queryset = queryset.filter_by_bbox(query_param['bbox'])
            if 'datetime' in query_param:
                queryset = queryset.filter_by_datetime(query_param['datetime'])
            if 'collections' in query_param:
                queryset = queryset.filter_by_collections(query_param['collections'])
            if 'query' in query_param:
                dict_query = json.loads(query_param['query'])
                queryset = queryset.filter_by_query(dict_query)
            if 'intersects' in query_param:
                queryset = queryset.filter_by_intersects(json.dumps(query_param['intersects']))
            if 'forecast:reference_datetime' in query_param:
                queryset = queryset.filter_by_forecast_reference_datetime(
                    query_param['forecast:reference_datetime']
                )
            if 'forecast:horizon' in query_param:
                queryset = queryset.filter_by_forecast_horizon(query_param['forecast:horizon'])
            if 'forecast:duration' in query_param:
                queryset = queryset.filter_by_forecast_duration(query_param['forecast:duration'])
            if 'forecast:variable' in query_param:
                queryset = queryset.filter_by_forecast_variable(query_param['forecast:variable'])
            if 'forecast:perturbed' in query_param:
                queryset = queryset.filter_by_forecast_perturbed(query_param['forecast:perturbed'])

        if settings.DEBUG_ENABLE_DB_EXPLAIN_ANALYZE:
            logger.debug(
                "Output of EXPLAIN.. ANALYZE from SearchList() view:\n%s",
                queryset.explain(verbose=True, analyze=True)
            )
            logger.debug("The corresponding SQL statement:\n%s", queryset.query)

        return queryset

    def list(self, request, *args, **kwargs):

        validate_search_request = ValidateSearchRequest()
        validate_search_request.validate(request)  # validate the search request
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {
            'type': 'FeatureCollection',
            'timeStamp': utc_aware(datetime.utcnow()),
            'features': serializer.data,
            'links': get_relation_links(request, self.name)
        }

        if page is not None:
            response = self.paginator.get_paginated_response(data, request)
        response = Response(data)

        return response

    def get(self, request, *args, **kwargs):
        response = self.list(request, *args, **kwargs)
        patch_collections_aggregate_cache_control_header(response)
        return response

    def post(self, request, *args, **kwargs):
        response = self.list(request, *args, **kwargs)
        return response


@api_view(['POST'])
@permission_classes((permissions.AllowAny,))
def recalculate_extent(request):
    call_calculate_extent()
    return Response()
