import logging
from datetime import UTC
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Prefetch
from django.db.models import Q
from django.db.models import Subquery
from django.utils import timezone

from rest_framework import generics
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework_condition import etag

from stac_api.models.collection import Collection
from stac_api.models.item import Asset
from stac_api.models.item import Item
from stac_api.serializers.item import AssetSerializer
from stac_api.serializers.item import ItemListSerializer
from stac_api.serializers.item import ItemSerializer
from stac_api.serializers.utils import get_relation_links
from stac_api.utils import get_asset_path
from stac_api.validators_view import validate_collection
from stac_api.validators_view import validate_item
from stac_api.validators_view import validate_renaming
from stac_api.views import mixins
from stac_api.views.filters import create_is_active_filter
from stac_api.views.general import get_etag

logger = logging.getLogger(__name__)


def get_item_etag(request, *args, **kwargs):
    '''Get the ETag for a item object

    The ETag is an UUID4 computed on each object changes (including relations; assets and links)
    '''
    tag = get_etag(
        Item.objects.filter(collection__name=kwargs['collection_name'], name=kwargs['item_name'])
    )

    if settings.DEBUG_ENABLE_DB_EXPLAIN_ANALYZE:
        logger.debug(
            "Output of EXPLAIN.. ANALYZE from get_item_etag():\n%s",
            Item.objects.filter(
                collection__name=kwargs['collection_name'], name=kwargs['item_name']
            ).explain(verbose=True, analyze=True)
        )
        logger.debug(
            "The corresponding SQL statement:\n%s",
            Item.objects.filter(
                collection__name=kwargs['collection_name'], name=kwargs['item_name']
            ).query
        )

    return tag


def get_asset_etag(request, *args, **kwargs):
    '''Get the ETag for a asset object

    The ETag is an UUID4 computed on each object changes
    '''
    tag = get_etag(
        Asset.objects.filter(
            item__collection__name=kwargs['collection_name'],
            item__name=kwargs['item_name'],
            name=kwargs['asset_name']
        )
    )

    if settings.DEBUG_ENABLE_DB_EXPLAIN_ANALYZE:
        logger.debug(
            "Output of EXPLAIN.. ANALYZE from get_asset_etag():\n%s",
            Asset.objects.filter(item__name=kwargs['item_name'],
                                 name=kwargs['asset_name']).explain(verbose=True, analyze=True)
        )
        logger.debug(
            "The corresponding SQL statement:\n%s",
            Asset.objects.filter(item__name=kwargs['item_name'], name=kwargs['asset_name']).query
        )

    return tag


class ItemsList(generics.GenericAPIView):
    serializer_class = ItemSerializer
    ordering = ['name']
    name = 'items-list'  # this name must match the name in urls.py

    def get_queryset(self):
        # filter based on the url
        queryset = Item.objects.filter(
            create_is_active_filter(),
            # Using a subquery to get the collection id and then filter on the id greatly improves
            # the performance over filtering by 'collection__name'.
            collection__id=Subquery(
                Collection.objects.filter(name=self.kwargs['collection_name']).values('id')
            )
        ).prefetch_related(Prefetch('assets', queryset=Asset.objects.order_by('name')), 'links')
        bbox = self.request.query_params.get('bbox', None)
        date_time = self.request.query_params.get('datetime', None)

        if bbox:
            queryset = queryset.filter_by_bbox(bbox)

        if date_time:
            queryset = queryset.filter_by_datetime(date_time)

        if settings.DEBUG_ENABLE_DB_EXPLAIN_ANALYZE:
            logger.debug(
                "Output of EXPLAIN.. ANALYZE from ItemList() view:\n%s",
                queryset.explain(verbose=True, analyze=True)
            )
            logger.debug("The corresponding SQL statement:\n%s", queryset.query)

        return queryset

    def list(self, request, *args, **kwargs):
        validate_collection(self.kwargs)
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {
            'type': 'FeatureCollection',
            'timeStamp': datetime.now(UTC),
            'features': serializer.data,
            'links': get_relation_links(request, self.name, [self.kwargs['collection_name']])
        }

        if page is not None:
            response = self.get_paginated_response(data)
        response = Response(data)

        # Patch catch control header
        mixins.patch_collection_cache_control_header(response, self.kwargs['collection_name'])

        return response

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            # Currently we only check that this header parameter is part of the request.
            # We don't do anything with it. The idea is that, like this, we already
            # have it in our interface from the get-go and the users don't need to change later.
            idempotency_key_param = "Idempotency-Key"
            idempotency_key = request.headers.get(idempotency_key_param)
            if not idempotency_key:
                code = status.HTTP_400_BAD_REQUEST
                message = {
                    "code": code, "description": f"No header parameter '{idempotency_key_param}'"
                }
                return Response(data=message, status=code)

            collection = Collection.objects.get(name=self.kwargs['collection_name'])
            serializer = ItemListSerializer(
                data=request.data,
                context={
                    "request": request,
                    "collection": collection,
                    "validate_href_reachability": False
                }
            )
            if not serializer.is_valid():
                code = status.HTTP_400_BAD_REQUEST
                message = {"code": code, "description": str(serializer.errors)}
                return Response(data=message, status=code)

            serializer.save(collection=collection)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Collection.DoesNotExist as exception:
            code = status.HTTP_404_NOT_FOUND
            message = {"code": code, "description": str(exception)}
            return Response(data=message, exception=True, status=code)
        except IntegrityError as exception:
            code = status.HTTP_400_BAD_REQUEST
            message = {"code": code, "description": str(exception)}
            return Response(data=message, exception=True, status=code)


class ItemDetail(
    generics.GenericAPIView,
    mixins.RetrieveModelWithCacheMixin,
    mixins.UpdateInsertModelMixin,
    mixins.DestroyModelMixin
):
    # this name must match the name in urls.py and is used by the DestroyModelMixin
    name = 'item-detail'
    serializer_class = ItemSerializer
    lookup_url_kwarg = "item_name"
    lookup_field = "name"

    def get_queryset(self):
        # filter based on the url
        queryset = Item.objects.filter(
            create_is_active_filter(),
            # Using a subquery to get the collection id and then filter on the id greatly improves
            # the performance over filtering by 'collection__name'.
            collection__id=Subquery(
                Collection.objects.filter(name=self.kwargs['collection_name']).values('id')
            )
        ).prefetch_related(Prefetch('assets', queryset=Asset.objects.order_by('name')), 'links')

        if settings.DEBUG_ENABLE_DB_EXPLAIN_ANALYZE:
            logger.debug(
                "Output of EXPLAIN.. ANALYZE from ItemDetail() view:\n%s",
                queryset.explain(verbose=True, analyze=True)
            )
            logger.debug("The corresponding SQL statement:\n%s", queryset.query)

        return queryset

    def perform_update(self, serializer):
        collection = get_object_or_404(Collection, name=self.kwargs['collection_name'])
        validate_renaming(
            serializer,
            self.kwargs['item_name'],
            extra_log={
                'request': self.request._request,  # pylint: disable=protected-access
                'collection': self.kwargs['collection_name'],
                'item': self.kwargs['item_name']
            }
        )
        serializer.save(collection=collection)

    def perform_upsert(self, serializer, lookup):
        collection = get_object_or_404(Collection, name=self.kwargs['collection_name'])
        validate_renaming(
            serializer,
            self.kwargs['item_name'],
            extra_log={
                'request': self.request._request,  # pylint: disable=protected-access
                'collection': self.kwargs['collection_name'],
                'item': self.kwargs['item_name']
            }
        )
        lookup['collection__name'] = collection.name
        return serializer.upsert(lookup, collection=collection)

    @etag(get_item_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_item_etag)
    def put(self, request, *args, **kwargs):
        return self.upsert(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_item_etag)
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_item_etag)
    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)


class AssetsList(generics.GenericAPIView):
    name = 'assets-list'  # this name must match the name in urls.py
    serializer_class = AssetSerializer
    pagination_class = None

    def get_queryset(self):
        # filter based on the url
        return Asset.objects.filter(
            item__collection__name=self.kwargs['collection_name'],
            item__name=self.kwargs['item_name']
        ).order_by('name')

    def get(self, request, *args, **kwargs):
        validate_item(self.kwargs)

        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)

        data = {
            'assets': serializer.data,
            'links':
                get_relation_links(
                    request, self.name, [self.kwargs['collection_name'], self.kwargs['item_name']]
                )
        }
        response = Response(data)

        # Patch cache control header
        mixins.patch_collection_cache_control_header(response, self.kwargs['collection_name'])
        return response


class AssetDetail(
    generics.GenericAPIView,
    mixins.RetrieveModelWithCacheMixin,
    mixins.UpdateInsertModelMixin,
    mixins.DestroyModelMixin,
):
    # this name must match the name in urls.py and is used by the DestroyModelMixin
    name = 'asset-detail'
    serializer_class = AssetSerializer
    lookup_url_kwarg = "asset_name"
    lookup_field = "name"

    def get_queryset(self):
        # filter based on the url
        return Asset.objects.filter(
            Q(item__properties_expires=None) | Q(item__properties_expires__gte=timezone.now()),
            item__collection__name=self.kwargs['collection_name'],
            item__name=self.kwargs['item_name']
        )

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs.setdefault('context', self.get_serializer_context())
        item = get_object_or_404(
            Item, collection__name=self.kwargs['collection_name'], name=self.kwargs['item_name']
        )
        serializer = serializer_class(*args, **kwargs)

        # for the validation the serializer needs to know the collection of the
        # item. In case of upserting, the asset doesn't exist and thus the collection
        # can't be read from the instance, which is why we pass the collection manually
        # here.
        serializer.collection = item.collection
        return serializer

    def _get_file_path(self, serializer, item, asset_name):
        """Get the path to the file

        If the collection allows for external asset, and the file is specified
        in the request, we set it directly. If the collection doesn't allow it,
        error 400.
        Otherwise we assemble the path from the file name, collection name as
        well as the s3 bucket domain
        """

        if 'file' in serializer.validated_data:
            file = serializer.validated_data['file']
            # setting the href makes the asset be external implicitly
            is_external = True
        else:
            file = get_asset_path(item, asset_name)
            is_external = False

        return file, is_external

    def perform_update(self, serializer):
        item = get_object_or_404(
            Item, collection__name=self.kwargs['collection_name'], name=self.kwargs['item_name']
        )
        validate_renaming(
            serializer,
            original_id=self.kwargs['asset_name'],
            extra_log={
                'request': self.request._request,  # pylint: disable=protected-access
                'collection': self.kwargs['collection_name'],
                'item': self.kwargs['item_name'],
                'asset': self.kwargs['asset_name']
            }
        )
        file, is_external = self._get_file_path(serializer, item, self.kwargs['asset_name'])
        return serializer.save(item=item, file=file, is_external=is_external)

    def perform_upsert(self, serializer, lookup):
        item = get_object_or_404(
            Item, collection__name=self.kwargs['collection_name'], name=self.kwargs['item_name']
        )

        validate_renaming(
            serializer,
            original_id=self.kwargs['asset_name'],
            extra_log={
                'request': self.request._request,  # pylint: disable=protected-access
                'collection': self.kwargs['collection_name'],
                'item': self.kwargs['item_name'],
                'asset': self.kwargs['asset_name']
            }
        )
        lookup['item__collection__name'] = item.collection.name
        lookup['item__name'] = item.name

        file, is_external = self._get_file_path(serializer, item, self.kwargs['asset_name'])
        return serializer.upsert(lookup, item=item, file=file, is_external=is_external)

    @etag(get_asset_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_asset_etag)
    def put(self, request, *args, **kwargs):
        return self.upsert(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_asset_etag)
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_asset_etag)
    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)
