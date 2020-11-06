import logging
from datetime import datetime
from datetime import timezone

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import Item
from stac_api.serializers import AssetSerializer
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import ItemSerializer

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


def landing_page(request):
    url_base = request.build_absolute_uri()
    # Somehow yapf 0.30.0 cannot format the data dictionary nicely with the links embedded array
    # it split the first key: value into two lines and add wrong indentation to the links items
    # therefore we disable yapf for this line here (see https://github.com/google/yapf/issues/392)
    # yapf: disable
    data = {
        "description": "Data Catalog of the Swiss Federal Spatial Data Infrastructure",
        "id": "ch",
        "stac_version": "0.9.0",
        "title": "data.geo.admin.ch",
        "links": [{
            "href": url_base,
            "rel": "self",
            "type": "application/json",
            "title": "this document",
        }, {
            "href": f"{url_base}api.html",
            "rel": "service-doc",
            "type": "text/html",
            "title": "the API documentation"
        }, {
            "href": f"{url_base}conformance",
            "rel": "conformance",
            "type": "application/json",
            "title": "OGC API conformance classes implemented by this server"
        }, {
            "href": f"{url_base}collections",
            "rel": "data",
            "type": "application/json",
            "title": "Information about the feature collections"
        }, {
            "href": f"{url_base}search",
            "rel": "search",
            "type": "application/json",
            "title": "Search across feature collections"
        }]
    }
    # yapf: enable

    logger.debug('Landing page', extra={'request': request, 'response': data})

    return JsonResponse(data)


def checker(request):
    data = {"success": True, "message": "OK"}

    return JsonResponse(data)


class CollectionList(generics.ListAPIView):
    serializer_class = CollectionSerializer
    queryset = Collection.objects.all()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {'collections': serializer.data}

        logger.debug('GET list of collections', extra={"request": request, "response": data})

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class CollectionDetail(generics.RetrieveAPIView):
    serializer_class = CollectionSerializer
    lookup_url_kwarg = "collection_name"
    queryset = Collection.objects.all()

    def get_object(self):
        collection_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(collection_name=collection_name)
        obj = get_object_or_404(queryset)
        return obj


class ItemsList(generics.ListAPIView):
    serializer_class = ItemSerializer
    queryset = Item.objects.all()

    def get_queryset(self):
        # filter based on the url
        queryset = Item.objects.filter(collection__collection_name=self.kwargs['collection_name'])

        bbox = self.request.query_params.get('bbox', None)
        date_time = self.request.query_params.get('datetime', None)

        if bbox:
            raise NotImplementedError('bbox query parameter not yet implemented')

        if date_time:
            queryset = self.filter_by_datetime(queryset, date_time)

        return queryset

    def filter_by_datetime(self, queryset, date_time):
        start, end = parse_datetime_query(date_time)

        if end is not None:
            raise ValidationError(_('Time range query not yet supported'))

        return queryset.filter(properties_datetime=start)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {
            'type': 'FeatureCollection',
            'timeStamp': datetime.utcnow().replace(tzinfo=timezone.utc),
            'features': serializer.data
        }

        logger.debug('GET list of items', extra={"request": request, "response": data})

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class ItemDetail(generics.RetrieveAPIView):
    serializer_class = ItemSerializer
    lookup_url_kwarg = "item_name"
    queryset = Item.objects.all()

    def get_object(self):
        item_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(item_name=item_name)
        obj = get_object_or_404(queryset)
        return obj


class AssetsList(generics.GenericAPIView):
    serializer_class = AssetSerializer
    queryset = Asset.objects.all()
    pagination_class = None

    def get_queryset(self):
        # filter based on the url
        return Asset.objects.filter(item__item_name=self.kwargs['item_name'])

    def get(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = serializer.data

        logger.debug('GET list of assets: %s', data, extra={"request": request, "response": data})

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class AssetDetail(generics.RetrieveAPIView):
    serializer_class = AssetSerializer
    lookup_url_kwarg = "asset_name"
    queryset = Asset.objects.all()

    def get_object(self):
        asset_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(asset_name=asset_name)
        obj = get_object_or_404(queryset)
        return obj


class TestHttp500(AssetDetail):

    def get(self, request, *args, **kwargs):
        logger.debug('Test request that raises an exception')

        raise AttributeError('test exception')
