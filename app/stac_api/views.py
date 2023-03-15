import json
import logging
from datetime import datetime
from operator import itemgetter

from django.conf import settings
from django.db import IntegrityError
from django.db import transaction
from django.db.models import Min
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _

from rest_framework import generics
from rest_framework import mixins
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_condition import etag

from stac_api import views_mixins
from stac_api.models import Asset
from stac_api.models import AssetUpload
from stac_api.models import Collection
from stac_api.models import ConformancePage
from stac_api.models import Item
from stac_api.models import LandingPage
from stac_api.pagination import ExtApiPagination
from stac_api.pagination import GetPostCursorPagination
from stac_api.s3_multipart_upload import MultipartUpload
from stac_api.serializers import AssetSerializer
from stac_api.serializers import AssetUploadPartsSerializer
from stac_api.serializers import AssetUploadSerializer
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import ConformancePageSerializer
from stac_api.serializers import ItemSerializer
from stac_api.serializers import LandingPageSerializer
from stac_api.serializers_utils import get_relation_links
from stac_api.utils import get_asset_path
from stac_api.utils import harmonize_post_get_for_search
from stac_api.utils import utc_aware
from stac_api.validators_serializer import ValidateSearchRequest
from stac_api.validators_view import validate_asset
from stac_api.validators_view import validate_collection
from stac_api.validators_view import validate_item
from stac_api.validators_view import validate_renaming

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


def get_asset_upload_etag(request, *args, **kwargs):
    '''Get the ETag for an asset upload object

    The ETag is an UUID4 computed on each object changes
    '''
    return get_etag(
        AssetUpload.objects.filter(
            asset__item__collection__name=kwargs['collection_name'],
            asset__item__name=kwargs['item_name'],
            asset__name=kwargs['asset_name'],
            upload_id=kwargs['upload_id']
        )
    )


class LandingPageDetail(generics.RetrieveAPIView):
    name = 'landing-page'  # this name must match the name in urls.py
    serializer_class = LandingPageSerializer
    queryset = LandingPage.objects.all()

    def get_object(self):
        return LandingPage.get_solo()


class ConformancePageDetail(generics.RetrieveAPIView):
    name = 'conformance'  # this name must match the name in urls.py
    serializer_class = ConformancePageSerializer
    queryset = ConformancePage.objects.all()

    def get_object(self):
        return ConformancePage.get_solo()


class SearchList(generics.GenericAPIView, mixins.ListModelMixin):
    name = 'search-list'  # this name must match the name in urls.py
    permission_classes = [AllowAny]
    serializer_class = ItemSerializer
    pagination_class = GetPostCursorPagination
    # It is important to order the result by a unique identifier, because the search endpoint
    # search overall collections and that the item name is only unique within a collection
    # we must use the pk as ordering attribute, otherwise the cursor pagination will not work
    ordering = ['pk']

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
        views_mixins.patch_cache_settings_by_update_interval(response, min_update_interval)
        return response

    def post(self, request, *args, **kwargs):
        response, _ = self.list(request, *args, **kwargs)
        return response


class CollectionList(generics.GenericAPIView):
    name = 'collections-list'  # this name must match the name in urls.py
    serializer_class = CollectionSerializer
    # prefetch_related is a performance optimization to reduce the number
    # of DB queries.
    # see https://docs.djangoproject.com/en/3.1/ref/models/querysets/#prefetch-related
    queryset = Collection.objects.filter(published=True).prefetch_related('providers', 'links')
    ordering = ['title']

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


class ItemsList(generics.GenericAPIView):
    serializer_class = ItemSerializer
    ordering = ['name']
    name = 'items-list'  # this name must match the name in urls.py

    def get_queryset(self):
        # filter based on the url
        queryset = Item.objects.filter(
            collection__name=self.kwargs['collection_name']
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
        update_interval = Collection.objects.values('update_interval').get(
            name=self.kwargs['collection_name']
        )['update_interval']
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {
            'type': 'FeatureCollection',
            'timeStamp': utc_aware(datetime.utcnow()),
            'features': serializer.data,
            'links': get_relation_links(request, self.name, [self.kwargs['collection_name']])
        }

        if page is not None:
            response = self.get_paginated_response(data)
        response = Response(data)
        views_mixins.patch_cache_settings_by_update_interval(response, update_interval)
        return response

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class ItemDetail(
    generics.GenericAPIView,
    views_mixins.RetrieveModelDynCacheMixin,
    views_mixins.UpdateInsertModelMixin,
    views_mixins.DestroyModelMixin
):
    # this name must match the name in urls.py and is used by the DestroyModelMixin
    name = 'item-detail'
    serializer_class = ItemSerializer
    lookup_url_kwarg = "item_name"
    lookup_field = "name"

    def get_queryset(self):
        # filter based on the url
        queryset = Item.objects.filter(
            collection__name=self.kwargs['collection_name']
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
        update_interval = Item.objects.values('update_interval').get(
            collection__name=self.kwargs['collection_name'],
            name=self.kwargs['item_name'],
        )['update_interval']
        serializer = self.get_serializer(queryset, many=True)

        data = {
            'assets': serializer.data,
            'links':
                get_relation_links(
                    request, self.name, [self.kwargs['collection_name'], self.kwargs['item_name']]
                )
        }
        response = Response(data)
        views_mixins.patch_cache_settings_by_update_interval(response, update_interval)
        return response


class AssetDetail(
    generics.GenericAPIView,
    views_mixins.UpdateInsertModelMixin,
    views_mixins.DestroyModelMixin,
    views_mixins.RetrieveModelDynCacheMixin
):
    # this name must match the name in urls.py and is used by the DestroyModelMixin
    name = 'asset-detail'
    serializer_class = AssetSerializer
    lookup_url_kwarg = "asset_name"
    lookup_field = "name"

    def get_queryset(self):
        # filter based on the url
        return Asset.objects.filter(
            item__collection__name=self.kwargs['collection_name'],
            item__name=self.kwargs['item_name']
        )

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs.setdefault('context', self.get_serializer_context())
        return serializer_class(*args, **kwargs)

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
        serializer.save(item=item, file=get_asset_path(item, self.kwargs['asset_name']))

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
        return serializer.upsert(
            lookup, item=item, file=get_asset_path(item, self.kwargs['asset_name'])
        )

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


class AssetUploadBase(generics.GenericAPIView):
    serializer_class = AssetUploadSerializer
    lookup_url_kwarg = "upload_id"
    lookup_field = "upload_id"

    def get_queryset(self):
        return AssetUpload.objects.filter(
            asset__item__collection__name=self.kwargs['collection_name'],
            asset__item__name=self.kwargs['item_name'],
            asset__name=self.kwargs['asset_name']
        ).prefetch_related('asset')

    def get_in_progress_queryset(self):
        return self.get_queryset().filter(status=AssetUpload.Status.IN_PROGRESS)

    def get_asset_or_404(self):
        return get_object_or_404(
            Asset.objects.all(),
            name=self.kwargs['asset_name'],
            item__name=self.kwargs['item_name'],
            item__collection__name=self.kwargs['collection_name']
        )

    def _save_asset_upload(self, executor, serializer, key, asset, upload_id, urls):
        try:
            with transaction.atomic():
                serializer.save(asset=asset, upload_id=upload_id, urls=urls)
        except IntegrityError as error:
            logger.error(
                'Failed to create asset upload multipart: %s',
                error,
                extra={
                    'collection': asset.item.collection.name,
                    'item': asset.item.name,
                    'asset': asset.name
                }
            )
            if bool(self.get_in_progress_queryset()):
                raise serializers.ValidationError(
                    code='unique', detail=_('Upload already in progress')
                ) from None
            raise

    def create_multipart_upload(self, executor, serializer, validated_data, asset):
        key = get_asset_path(asset.item, asset.name)
        upload_id = executor.create_multipart_upload(
            key, asset, validated_data['checksum_multihash'], validated_data['update_interval']
        )
        urls = []
        sorted_md5_parts = sorted(validated_data['md5_parts'], key=itemgetter('part_number'))

        try:
            for part in sorted_md5_parts:
                urls.append(
                    executor.create_presigned_url(
                        key, asset, part['part_number'], upload_id, part['md5']
                    )
                )

            self._save_asset_upload(executor, serializer, key, asset, upload_id, urls)
        except serializers.ValidationError as err:
            executor.abort_multipart_upload(key, asset, upload_id)
            raise

    def complete_multipart_upload(self, executor, validated_data, asset_upload, asset):
        key = get_asset_path(asset.item, asset.name)
        parts = validated_data.get('parts', None)
        if parts is None:
            raise serializers.ValidationError({
                'parts': _("Missing required field")
            }, code='missing')
        if len(parts) > asset_upload.number_parts:
            raise serializers.ValidationError({'parts': [_("Too many parts")]}, code='invalid')
        if len(parts) < asset_upload.number_parts:
            raise serializers.ValidationError({'parts': [_("Too few parts")]}, code='invalid')
        executor.complete_multipart_upload(key, asset, parts, asset_upload.upload_id)
        asset_upload.update_asset_from_upload()
        asset_upload.status = AssetUpload.Status.COMPLETED
        asset_upload.ended = utc_aware(datetime.utcnow())
        asset_upload.urls = []
        asset_upload.save()

    def abort_multipart_upload(self, executor, asset_upload, asset):
        key = get_asset_path(asset.item, asset.name)
        executor.abort_multipart_upload(key, asset, asset_upload.upload_id)
        asset_upload.status = AssetUpload.Status.ABORTED
        asset_upload.ended = utc_aware(datetime.utcnow())
        asset_upload.urls = []
        asset_upload.save()

    def list_multipart_upload_parts(self, executor, asset_upload, asset, limit, offset):
        key = get_asset_path(asset.item, asset.name)
        return executor.list_upload_parts(key, asset, asset_upload.upload_id, limit, offset)


class AssetUploadsList(AssetUploadBase, mixins.ListModelMixin, views_mixins.CreateModelMixin):

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        validate_asset(self.kwargs)
        return self.list(request, *args, **kwargs)

    def get_success_headers(self, data):
        return {'Location': '/'.join([self.request.build_absolute_uri(), data['upload_id']])}

    def perform_create(self, serializer):
        executor = MultipartUpload()
        data = serializer.validated_data
        asset = self.get_asset_or_404()
        self.create_multipart_upload(executor, serializer, data, asset)

    def get_queryset(self):
        queryset = super().get_queryset()

        status = self.request.query_params.get('status', None)
        if status:
            queryset = queryset.filter_by_status(status)

        return queryset


class AssetUploadDetail(AssetUploadBase, mixins.RetrieveModelMixin, views_mixins.DestroyModelMixin):

    @etag(get_asset_upload_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    # @etag(get_asset_upload_etag)
    # def delete(self, request, *args, **kwargs):
    #     return self.destroy(request, *args, **kwargs)


class AssetUploadComplete(AssetUploadBase, views_mixins.UpdateInsertModelMixin):

    def post(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def perform_update(self, serializer):
        executor = MultipartUpload()
        asset = serializer.instance.asset
        self.complete_multipart_upload(
            executor, serializer.validated_data, serializer.instance, asset
        )


class AssetUploadAbort(AssetUploadBase, views_mixins.UpdateInsertModelMixin):

    def post(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def perform_update(self, serializer):
        executor = MultipartUpload()
        asset = serializer.instance.asset
        self.abort_multipart_upload(executor, serializer.instance, asset)


class AssetUploadPartsList(AssetUploadBase):
    serializer_class = AssetUploadPartsSerializer
    pagination_class = ExtApiPagination

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        executor = MultipartUpload()
        asset_upload = self.get_object()
        limit, offset = self.get_pagination_config(request)
        data, has_next = self.list_multipart_upload_parts(
            executor, asset_upload, asset_upload.asset, limit, offset
        )
        serializer = self.get_serializer(data)

        return self.get_paginated_response(serializer.data, has_next)

    def get_pagination_config(self, request):
        return self.paginator.get_pagination_config(request)

    def get_paginated_response(self, data, has_next):  # pylint: disable=arguments-differ
        return self.paginator.get_paginated_response(data, has_next)
