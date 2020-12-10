import logging
from collections import OrderedDict
from datetime import datetime

from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

from rest_framework import generics
from rest_framework import mixins
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from stac_api import views_mixins
from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import ConformancePage
from stac_api.models import Item
from stac_api.models import LandingPage
from stac_api.serializers import AssetSerializer
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import ConformancePageSerializer
from stac_api.serializers import ItemSerializer
from stac_api.serializers import LandingPageSerializer
from stac_api.utils import utc_aware

logger = logging.getLogger(__name__)


def parse_datetime_query(date_time):
    '''Parse the datetime query as specified in the api-spec.md.

    Returns one of the following
        datetime, None
        datetime, '..'
        '..', datetime
        datetime, datetime
    '''
    start, sep, end = date_time.partition('/')
    try:
        if start != '..':
            start = datetime.fromisoformat(start.replace('Z', '+00:00'))
        if end and end != '..':
            end = datetime.fromisoformat(end.replace('Z', '+00:00'))
    except ValueError as error:
        logger.error(
            'Invalid datetime query parameter "%s", must be isoformat; %s', date_time, error
        )
        raise ValidationError(_('Invalid datetime query parameter, must be isoformat'))

    if end == '':
        end = None

    if start == '..' and (end is None or end == '..'):
        logger.error(
            'Invalid datetime query parameter "%s"; '
            'cannot start with open range when no end range is defined',
            date_time
        )
        raise ValidationError(_('Invalid datetime query parameter, '
                                'cannot start with open range when no end range is defined'))
    return start, end


class LandingPageDetail(generics.RetrieveAPIView):
    serializer_class = LandingPageSerializer
    queryset = LandingPage.objects.all()

    def get_object(self):
        return LandingPage.get_solo()


class ConformancePageDetail(generics.RetrieveAPIView):
    serializer_class = ConformancePageSerializer
    queryset = ConformancePage.objects.all()

    def get_object(self):
        return ConformancePage.get_solo()


def checker(request):
    data = {"success": True, "message": "OK"}

    return JsonResponse(data)


class CollectionList(generics.ListAPIView, mixins.CreateModelMixin):
    serializer_class = CollectionSerializer
    queryset = Collection.objects.all()

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {
            'collections': serializer.data,
            'links': [
                OrderedDict([
                    ('rel', 'self'),
                    ('href', request.build_absolute_uri()),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', request.build_absolute_uri(f'/{settings.API_BASE}/')),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    ('href', request.build_absolute_uri('.')),
                ])
            ]
        }

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class CollectionDetail(generics.GenericAPIView, mixins.RetrieveModelMixin, mixins.UpdateModelMixin):
    serializer_class = CollectionSerializer
    lookup_url_kwarg = "collection_name"
    queryset = Collection.objects.all()

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def get_object(self):
        collection_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(name=collection_name)
        obj = get_object_or_404(queryset)
        return obj


class ItemsList(generics.GenericAPIView, views_mixins.CreateModelMixin):
    serializer_class = ItemSerializer
    queryset = Item.objects.all()

    def get_write_request_data(self, request, *args, **kwargs):
        data = request.data.copy()
        data['collection'] = kwargs['collection_name']
        return data

    def get_queryset(self):
        # filter based on the url
        queryset = Item.objects.filter(collection__name=self.kwargs['collection_name'])

        bbox = self.request.query_params.get('bbox', None)
        date_time = self.request.query_params.get('datetime', None)

        if bbox:
            queryset = self.filter_by_bbox(queryset, bbox)

        if date_time:
            queryset = self.filter_by_datetime(queryset, date_time)

        return queryset

    def filter_by_bbox(self, queryset, bbox):
        try:
            logger.debug('Item query parameter bbox = %s', bbox)
            query_bbox_polygon = Polygon.from_bbox(bbox.split(','))
        except ValueError as error:
            logger.error(
                'Invalid bbox parameter: '
                'Could not transform bbox "%s" to a polygon; %s'
                'f.ex. bbox=5.96, 45.82, 10.49, 47.81',
                bbox,
                error
            )
            raise ValidationError(_('Invalid bbox query parameter, '
                                    ' has to contain 4 values. f.ex. bbox=5.96,45.82,10.49,47.81'))

        return queryset.filter(geometry__intersects=query_bbox_polygon)

    def filter_by_datetime(self, queryset, date_time):
        start, end = parse_datetime_query(date_time)

        if end is not None:
            return self.filter_by_datetime_range(queryset, start, end)

        return queryset.filter(properties_datetime=start)

    def filter_by_datetime_range(self, queryset, start_datetime, end_datetime):
        if start_datetime == '..':
            # open start range
            queryset1 = queryset.filter(properties_datetime__lte=end_datetime)
            queryset2 = queryset.filter(properties_end_datetime__lte=end_datetime)
            return queryset1.union(queryset2)
        if end_datetime == '..':
            # open end range
            queryset1 = queryset.filter(properties_datetime__gte=start_datetime)
            queryset2 = queryset.filter(properties_end_datetime__gte=start_datetime)
            return queryset1.union(queryset2)
        # else fixed range
        queryset1 = queryset.filter(properties_datetime__range=(start_datetime, end_datetime))
        queryset2 = queryset.filter(
            properties_start_datetime__gte=start_datetime,
            properties_end_datetime__lte=end_datetime
        )
        return queryset1.union(queryset2)

    def list(self, request, *args, **kwargs):
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
            'links': [
                OrderedDict([
                    ('rel', 'self'),
                    ('href', request.build_absolute_uri()),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', request.build_absolute_uri(f'/{settings.API_BASE}/')),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    ('href', request.build_absolute_uri('.').rstrip('/')),
                ])
            ]
        }

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)


class ItemDetail(
    generics.GenericAPIView,
    mixins.RetrieveModelMixin,
    views_mixins.UpdateModelMixin,
    views_mixins.DestroyModelMixin
):
    serializer_class = ItemSerializer
    lookup_url_kwarg = "item_name"
    queryset = Item.objects.all()

    def get_write_request_data(self, request, *args, **kwargs):
        data = request.data.copy()
        data['collection'] = kwargs['collection_name']
        return data

    def get_object(self):
        item_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(name=item_name)
        obj = get_object_or_404(queryset)
        return obj

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)


class AssetsList(generics.GenericAPIView):
    serializer_class = AssetSerializer
    queryset = Asset.objects.all()
    pagination_class = None

    def get_queryset(self):
        # filter based on the url
        return Asset.objects.filter(item__name=self.kwargs['item_name'])

    def get(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = serializer.data

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class AssetDetail(generics.RetrieveAPIView):
    serializer_class = AssetSerializer
    lookup_url_kwarg = "asset_name"
    queryset = Asset.objects.all()

    def get_object(self):
        asset_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(name=asset_name)
        obj = get_object_or_404(queryset)
        return obj


class TestHttp500(AssetDetail):

    def get(self, request, *args, **kwargs):
        logger.debug('Test request that raises an exception')

        raise AttributeError('test exception')
