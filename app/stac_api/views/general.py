import json
import logging
from datetime import datetime

from django.conf import settings
from django.db.models import Min
from django.utils.translation import gettext_lazy as _

from rest_framework import generics
from rest_framework import mixins
from rest_framework import permissions
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from stac_api.models import Item
from stac_api.models import LandingPage
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
from stac_api.views.mixins import patch_cache_settings_by_update_interval

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
        queryset = Item.objects.filter(collection__published=True
                                      ).prefetch_related('assets', 'links')
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

    def get_min_update_interval(self, queryset):
        update_interval = queryset.filter(update_interval__gt=-1
                                         ).aggregate(Min('update_interval')
                                                    ).get('update_interval__min', None)
        if update_interval is None:
            update_interval = -1
        return update_interval

    def list(self, request, *args, **kwargs):

        validate_search_request = ValidateSearchRequest()
        validate_search_request.validate(request)  # validate the search request
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        min_update_interval = None
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            if page is None:
                queryset_paginated = queryset
            else:
                queryset_paginated = Item.objects.filter(pk__in=map(lambda item: item.pk, page))
            min_update_interval = self.get_min_update_interval(queryset_paginated)

        data = {
            'type': 'FeatureCollection',
            'timeStamp': utc_aware(datetime.utcnow()),
            'features': serializer.data,
            'links': get_relation_links(request, self.name)
        }

        if page is not None:
            response = self.paginator.get_paginated_response(data, request)
        response = Response(data)

        return response, min_update_interval

    def get(self, request, *args, **kwargs):
        response, min_update_interval = self.list(request, *args, **kwargs)
        patch_cache_settings_by_update_interval(response, min_update_interval)
        return response

    def post(self, request, *args, **kwargs):
        response, _ = self.list(request, *args, **kwargs)
        return response


@api_view(['POST'])
@permission_classes((permissions.AllowAny,))
def recalculate_extent(request):
    call_calculate_extent()
    return Response()
