import json
import logging
from collections import OrderedDict
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from rest_framework import generics
from rest_framework import mixins
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_condition import etag

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
from stac_api.utils import harmonize_post_get_for_search
from stac_api.utils import utc_aware
from stac_api.validators import ValidateSearchRequest

logger = logging.getLogger(__name__)


def get_etag(queryset):
    if queryset.exists():
        return list(queryset.only('etag').values('etag').first().values())[0]
    return None


def get_collection_etag(request, *args, **kwargs):
    '''Get the ETag for a collection object

    The ETag is an UUID4 computed on each object changes (including relations; provider and links)
    '''
    tag = get_etag(Collection.objects.filter(name=kwargs['collection_name']))
    return tag


def get_item_etag(request, *args, **kwargs):
    '''Get the ETag for a item object

    The ETag is an UUID4 computed on each object changes (including relations; assets and links)
    '''
    tag = get_etag(
        Item.objects.filter(collection__name=kwargs['collection_name'], name=kwargs['item_name'])
    )
    return tag


def get_asset_etag(request, *args, **kwargs):
    '''Get the ETag for a asset object

    The ETag is an UUID4 computed on each object changes
    '''
    tag = get_etag(Asset.objects.filter(item__name=kwargs['item_name'], name=kwargs['asset_name']))
    return tag


def checker(request):
    data = {"success": True, "message": "OK"}

    return JsonResponse(data)


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


class CollectionList(generics.GenericAPIView, views_mixins.CreateModelMixin):
    serializer_class = CollectionSerializer
    # prefetch_related is a performance optimization to reduce the number
    # of DB queries.
    # see https://docs.djangoproject.com/en/3.1/ref/models/querysets/#prefetch-related
    queryset = Collection.objects.all().prefetch_related('providers', 'links')

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

    @etag(get_collection_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_collection_etag)
    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_collection_etag)
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def get_object(self):
        collection_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(name=collection_name)
        obj = get_object_or_404(queryset)
        return obj


class ItemsList(generics.GenericAPIView, views_mixins.CreateModelMixin):
    serializer_class = ItemSerializer

    def get_write_request_data(self, request, *args, **kwargs):
        data = request.data.copy()
        data['collection'] = kwargs['collection_name']
        return data

    def get_queryset(self):
        # filter based on the url
        queryset = Item.objects.filter(collection__name=self.kwargs['collection_name']
                                      ).prefetch_related('assets', 'links')

        bbox = self.request.query_params.get('bbox', None)
        date_time = self.request.query_params.get('datetime', None)

        if bbox:
            queryset = queryset.filter_by_bbox(bbox)

        if date_time:
            queryset = queryset.filter_by_datetime(date_time)

        return queryset

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

    def get_queryset(self):
        # filter based on the url
        queryset = Item.objects.filter(collection__name=self.kwargs['collection_name']
                                      ).prefetch_related('assets', 'links')
        return queryset

    def get_write_request_data(self, request, *args, partial=False, **kwargs):
        data = request.data.copy()
        data['collection'] = kwargs['collection_name']
        return data

    def get_object(self):
        item_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(name=item_name)
        obj = get_object_or_404(queryset)
        return obj

    @etag(get_item_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_item_etag)
    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_item_etag)
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_item_etag)
    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)


class SearchList(generics.GenericAPIView, mixins.ListModelMixin):
    permission_classes = [AllowAny]
    serializer_class = ItemSerializer

    def get_queryset(self):
        queryset = Item.objects.all()
        # harmonize GET and POST query
        query_param = harmonize_post_get_for_search(self.request)

        # build queryset

        # if ids, then the other params will be ignored
        if 'ids' in query_param:
            queryset = queryset.filter_by_ids(query_param['ids'])
        else:
            if 'bbox' in query_param:
                queryset = queryset.filter_by_bbox(query_param['bbox'])
            if 'datetime' in query_param:
                queryset = queryset.filter_by_datetime(query_param['datetime'])
            if 'collections' in query_param:
                queryset = queryset.filter_by_collections(query_param['collections'])
            if 'query' in query_param:
                queryset = queryset.filter_by_query(query_param['query'])
            if 'intersects' in query_param:
                queryset = queryset.filter_by_intersects(json.dumps(query_param['intersects']))

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
        return self.list(request, *args, **kwargs)


class AssetsList(generics.GenericAPIView, views_mixins.CreateModelMixin):
    serializer_class = AssetSerializer
    pagination_class = None

    def get_write_request_data(self, request, *args, **kwargs):
        data = request.data.copy()
        data['item'] = kwargs['item_name']
        return data

    def get_success_headers(self, data):  # pylint: disable=arguments-differ
        asset_link_self = self.request.build_absolute_uri() + "/" + self.request.data["id"]
        return {'Location': asset_link_self}

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def get_queryset(self):
        # filter based on the url
        return Asset.objects.filter(
            item__collection__name=self.kwargs['collection_name'],
            item__name=self.kwargs['item_name']
        )

    def get(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {
            'assets': serializer.data,
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
                ]),
                OrderedDict([
                    ('rel', 'item'),
                    ('href', request.build_absolute_uri('.').rstrip('/')),
                ]),
                OrderedDict([
                    ('rel', 'collection'),
                    ('href', request.build_absolute_uri('../..').rstrip('/')),
                ])
            ]
        }

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class AssetDetail(
    generics.GenericAPIView,
    mixins.RetrieveModelMixin,
    views_mixins.UpdateModelMixin,
    views_mixins.DestroyModelMixin
):
    serializer_class = AssetSerializer
    lookup_url_kwarg = "asset_name"

    def get_write_request_data(self, request, *args, partial=False, **kwargs):
        data = request.data.copy()
        data['item'] = kwargs['item_name']
        if partial and not 'id' in data:
            # Partial update for checksum:multihash requires the asset id in order to verify the
            # file with the checksum, therefore if the id is missing in payload we take it from
            # the request path.
            data['id'] = kwargs['asset_name']
        return data

    def get_queryset(self):
        # filter based on the url
        return Asset.objects.filter(
            item__collection__name=self.kwargs['collection_name'],
            item__name=self.kwargs['item_name']
        )

    def get_object(self):
        asset_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(name=asset_name)
        obj = get_object_or_404(queryset)
        return obj

    def get_serializer(self, *args, **kwargs):
        hide_fields = kwargs.pop('hide_fields', [])
        serializer_class = self.get_serializer_class()
        kwargs.setdefault('context', self.get_serializer_context())
        return serializer_class(*args, hide_fields=hide_fields, **kwargs)

    @etag(get_asset_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_asset_etag)
    def put(self, request, *args, **kwargs):
        return self.update(request, *args, hide_fields=['href'], **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_asset_etag)
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, hide_fields=['href'], **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_asset_etag)
    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)


class TestHttp500(AssetDetail):

    def get(self, request, *args, **kwargs):
        logger.debug('Test request that raises an exception')

        raise AttributeError('test exception')
