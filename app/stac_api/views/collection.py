import logging

from django.conf import settings

from rest_framework import generics
from rest_framework import mixins
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework_condition import etag

from stac_api.models import Collection
from stac_api.models import CollectionAsset
from stac_api.serializers import CollectionAssetSerializer
from stac_api.serializers import CollectionSerializer
from stac_api.serializers_utils import get_relation_links
from stac_api.utils import get_collection_asset_path
from stac_api.validators_view import validate_collection
from stac_api.validators_view import validate_renaming
from stac_api.views import views_mixins
from stac_api.views.views import get_etag

logger = logging.getLogger(__name__)


def get_collection_etag(request, *args, **kwargs):
    '''Get the ETag for a collection object

    The ETag is an UUID4 computed on each object changes (including relations; provider and links)
    '''
    tag = get_etag(Collection.objects.filter(name=kwargs['collection_name']))

    if settings.DEBUG_ENABLE_DB_EXPLAIN_ANALYZE:
        logger.debug(
            "Output of EXPLAIN.. ANALYZE from get_collection_etag():\n%s",
            Collection.objects.filter(name=kwargs['collection_name']
                                     ).explain(verbose=True, analyze=True)
        )
        logger.debug(
            "The corresponding SQL statement:\n%s",
            Collection.objects.filter(name=kwargs['collection_name']).query
        )

    return tag


def get_collection_asset_etag(request, *args, **kwargs):
    '''Get the ETag for a collection asset object

    The ETag is an UUID4 computed on each object changes
    '''
    tag = get_etag(
        CollectionAsset.objects.filter(
            collection__name=kwargs['collection_name'], name=kwargs['asset_name']
        )
    )

    if settings.DEBUG_ENABLE_DB_EXPLAIN_ANALYZE:
        logger.debug(
            "Output of EXPLAIN.. ANALYZE from get_collection_asset_etag():\n%s",
            CollectionAsset.objects.filter(name=kwargs['asset_name']
                                          ).explain(verbose=True, analyze=True)
        )
        logger.debug(
            "The corresponding SQL statement:\n%s",
            CollectionAsset.objects.filter(name=kwargs['asset_name']).query
        )

    return tag


class CollectionList(generics.GenericAPIView):
    name = 'collections-list'  # this name must match the name in urls.py
    serializer_class = CollectionSerializer
    # prefetch_related is a performance optimization to reduce the number
    # of DB queries.
    # see https://docs.djangoproject.com/en/3.1/ref/models/querysets/#prefetch-related
    queryset = Collection.objects.filter(published=True).prefetch_related('providers', 'links')
    ordering = ['name']

    def get(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {'collections': serializer.data, 'links': get_relation_links(request, self.name)}

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class CollectionDetail(
    generics.GenericAPIView,
    mixins.RetrieveModelMixin,
    views_mixins.UpdateInsertModelMixin,
    views_mixins.DestroyModelMixin
):
    # this name must match the name in urls.py and is used by the DestroyModelMixin
    name = 'collection-detail'
    serializer_class = CollectionSerializer
    lookup_url_kwarg = "collection_name"
    lookup_field = "name"
    queryset = Collection.objects.all().prefetch_related('providers', 'links')

    @etag(get_collection_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_collection_etag)
    def put(self, request, *args, **kwargs):
        return self.upsert(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_collection_etag)
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_collection_etag)
    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)

    def perform_upsert(self, serializer, lookup):
        validate_renaming(
            serializer,
            self.kwargs['collection_name'],
            extra_log={
                # pylint: disable=protected-access
                'request': self.request._request,
                'collection': self.kwargs['collection_name']
            }
        )
        return super().perform_upsert(serializer, lookup)

    def perform_update(self, serializer, *args, **kwargs):
        validate_renaming(
            serializer,
            self.kwargs['collection_name'],
            extra_log={
                # pylint: disable=protected-access
                'request': self.request._request,
                'collection': self.kwargs['collection_name']
            }
        )
        return super().perform_update(serializer, *args, **kwargs)


class CollectionAssetsList(generics.GenericAPIView):
    name = 'collection-assets-list'  # this name must match the name in urls.py
    serializer_class = CollectionAssetSerializer
    pagination_class = None

    def get_queryset(self):
        # filter based on the url
        return CollectionAsset.objects.filter(collection__name=self.kwargs['collection_name']
                                             ).order_by('name')

    def get(self, request, *args, **kwargs):
        validate_collection(self.kwargs)

        queryset = self.filter_queryset(self.get_queryset())
        update_interval = Collection.objects.values('update_interval').get(
            name=self.kwargs['collection_name']
        )['update_interval']
        serializer = self.get_serializer(queryset, many=True)

        data = {
            'assets': serializer.data,
            'links': get_relation_links(request, self.name, [self.kwargs['collection_name']])
        }
        response = Response(data)
        views_mixins.patch_cache_settings_by_update_interval(response, update_interval)
        return response


class CollectionAssetDetail(
    generics.GenericAPIView,
    views_mixins.UpdateInsertModelMixin,
    views_mixins.DestroyModelMixin,
    views_mixins.RetrieveModelDynCacheMixin
):
    # this name must match the name in urls.py and is used by the DestroyModelMixin
    name = 'collection-asset-detail'
    serializer_class = CollectionAssetSerializer
    lookup_url_kwarg = "asset_name"
    lookup_field = "name"

    def get_queryset(self):
        # filter based on the url
        return CollectionAsset.objects.filter(collection__name=self.kwargs['collection_name'])

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs.setdefault('context', self.get_serializer_context())
        collection = get_object_or_404(Collection, name=self.kwargs['collection_name'])
        serializer = serializer_class(*args, **kwargs)

        # for the validation the serializer needs to know the collection of the
        # asset. In case of inserting, the asset doesn't exist and thus the collection
        # can't be read from the instance, which is why we pass the collection manually
        # here. See serializers.AssetBaseSerializer._validate_href_field
        serializer.collection = collection
        return serializer

    def perform_update(self, serializer):
        collection = get_object_or_404(Collection, name=self.kwargs['collection_name'])
        validate_renaming(
            serializer,
            original_id=self.kwargs['asset_name'],
            extra_log={
                'request': self.request._request,  # pylint: disable=protected-access
                'collection': self.kwargs['collection_name'],
                'asset': self.kwargs['asset_name']
            }
        )
        return serializer.save(
            collection=collection,
            file=get_collection_asset_path(collection, self.kwargs['asset_name'])
        )

    def perform_upsert(self, serializer, lookup):
        collection = get_object_or_404(Collection, name=self.kwargs['collection_name'])
        validate_renaming(
            serializer,
            original_id=self.kwargs['asset_name'],
            extra_log={
                'request': self.request._request,  # pylint: disable=protected-access
                'collection': self.kwargs['collection_name'],
                'asset': self.kwargs['asset_name']
            }
        )
        lookup['collection__name'] = collection.name

        return serializer.upsert(
            lookup,
            collection=collection,
            file=get_collection_asset_path(collection, self.kwargs['asset_name'])
        )

    @etag(get_collection_asset_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_collection_asset_etag)
    def put(self, request, *args, **kwargs):
        return self.upsert(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_collection_asset_etag)
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_collection_asset_etag)
    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)
