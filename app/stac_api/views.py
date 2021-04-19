import json
import logging
from collections import OrderedDict
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from rest_framework import generics
from rest_framework import mixins
from rest_framework.exceptions import ValidationError
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
    serializer_class = LandingPageSerializer
    queryset = LandingPage.objects.all()

    def get_object(self):
        return LandingPage.get_solo()


class ConformancePageDetail(generics.RetrieveAPIView):
    serializer_class = ConformancePageSerializer
    queryset = ConformancePage.objects.all()

    def get_object(self):
        return ConformancePage.get_solo()


class SearchList(generics.GenericAPIView, mixins.ListModelMixin):
    permission_classes = [AllowAny]
    serializer_class = ItemSerializer
    pagination_class = GetPostCursorPagination

    def get_queryset(self):
        queryset = Item.objects.all().prefetch_related('assets', 'links')
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
                    ('href', request.build_absolute_uri(f'/{settings.STAC_BASE_V}/')),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    ('href', request.build_absolute_uri('.').rstrip('/')),
                ])
            ]
        }

        if page is not None:
            return self.paginator.get_paginated_response(data, request)
        return Response(data)

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


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
                    ('href', request.build_absolute_uri(f'/{settings.STAC_BASE_V}/')),
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


class CollectionDetail(
    generics.GenericAPIView,
    mixins.RetrieveModelMixin,
    views_mixins.UpdateInsertModelMixin,
    views_mixins.DestroyModelMixin
):
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
    # @etag(get_collection_etag)
    # def delete(self, request, *args, **kwargs):
    #     return self.destroy(request, *args, **kwargs)

    def perform_upsert(self, serializer, lookup):
        validate_renaming(
            serializer,
            'name',
            self.kwargs['collection_name'], {'collection': self.kwargs['collection_name']}
        )
        return super().perform_upsert(serializer, lookup)

    def perform_update(self, serializer, *args, **kwargs):
        validate_renaming(
            serializer,
            'name',
            self.kwargs['collection_name'], {'collection': self.kwargs['collection_name']}
        )
        return super().perform_update(serializer, *args, **kwargs)


class ItemsList(generics.GenericAPIView, views_mixins.CreateModelMixin):
    serializer_class = ItemSerializer

    def perform_create(self, serializer):
        # this DB hit used to be done by the serializer due to the SlugRelatedField during
        # deserialization
        collection = get_object_or_404(Collection, name=self.kwargs['collection_name'])
        serializer.save(collection=collection)

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
            'timeStamp': utc_aware(datetime.utcnow()),
            'features': serializer.data,
            'links': [
                OrderedDict([
                    ('rel', 'self'),
                    ('href', request.build_absolute_uri()),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', request.build_absolute_uri(f'/{settings.STAC_BASE_V}/')),
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
    views_mixins.UpdateInsertModelMixin,
    views_mixins.DestroyModelMixin
):
    serializer_class = ItemSerializer
    lookup_url_kwarg = "item_name"
    lookup_field = "name"

    def get_queryset(self):
        # filter based on the url
        queryset = Item.objects.filter(collection__name=self.kwargs['collection_name']
                                      ).prefetch_related('assets', 'links')

        if settings.DEBUG_ENABLE_DB_EXPLAIN_ANALYZE:
            logger.debug(
                "Output of EXPLAIN.. ANALYZE from ItemDetail() view:\n%s",
                queryset.explain(verbose=True, analyze=True)
            )
            logger.debug("The corresponding SQL statement:\n%s", queryset.query)

        return queryset

    def perform_update(self, serializer):
        collection = get_object_or_404(Collection, name=self.kwargs['collection_name'])
        serializer.save(collection=collection)

    def perform_upsert(self, serializer, lookup):
        collection = get_object_or_404(Collection, name=self.kwargs['collection_name'])
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


class AssetsList(generics.GenericAPIView, views_mixins.CreateModelMixin):
    serializer_class = AssetSerializer
    pagination_class = None

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

    def perform_create(self, serializer):
        # this DB hit used to done by the serializer due to the SlugRelatedField during
        # deserialization
        item = get_object_or_404(
            Item, collection__name=self.kwargs['collection_name'], name=self.kwargs['item_name']
        )
        serializer.save(item=item, file=get_asset_path(item, serializer.validated_data['name']))

    def get(self, request, *args, **kwargs):
        validate_item(self.kwargs)

        queryset = self.filter_queryset(self.get_queryset())
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
                    ('href', request.build_absolute_uri(f'/{settings.STAC_BASE_V}/')),
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
        return Response(data)


class AssetDetail(
    generics.GenericAPIView,
    mixins.RetrieveModelMixin,
    views_mixins.UpdateInsertModelMixin,
    views_mixins.DestroyModelMixin
):
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
            id_field='name',
            original_id=self.kwargs['asset_name'],
            extra_log=self.request
        )
        serializer.save(item=item, file=get_asset_path(item, self.kwargs['asset_name']))

    def perform_upsert(self, serializer, lookup):
        item = get_object_or_404(
            Item, collection__name=self.kwargs['collection_name'], name=self.kwargs['item_name']
        )
        validate_renaming(
            serializer,
            id_field='name',
            original_id=self.kwargs['asset_name'],
            extra_log=self.request
        )
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

    def create_multipart_upload(self, executor, serializer, validated_data, asset):
        key = get_asset_path(asset.item, asset.name)
        upload_id = executor.create_multipart_upload(
            key, asset, validated_data['checksum_multihash']
        )
        urls = []
        for part in range(
            1, (validated_data['number_parts'] if 'number_parts' in validated_data else 0) + 1
        ):
            urls.append(executor.create_presigned_url(key, asset, part, upload_id))

        clean_up_required = False
        try:
            with transaction.atomic():
                serializer.save(asset=asset, upload_id=upload_id, urls=urls)
        except IntegrityError as error:
            exception_handled = False
            clean_up_required = True
            logger.error(
                'Failed to create asset upload multipart: %s',
                error,
                extra={
                    'collection': asset.item.collection.name,
                    'item': asset.item.name,
                    'asset': asset.name
                }
            )
            in_progress = self.get_in_progress_queryset()
            if bool(in_progress):
                # Abort the last upload in progress and retry
                self.abort_multipart_upload(executor, in_progress.get(), asset)
                # And retry to save the new upload
                serializer.save(asset=asset, upload_id=upload_id, urls=urls)
                exception_handled = True
                clean_up_required = False
            if not exception_handled:
                raise
        finally:
            if clean_up_required:
                executor.abort_multipart_upload(key, asset, upload_id)

    def complete_multipart_upload(self, executor, validated_data, asset_upload, asset):
        key = get_asset_path(asset.item, asset.name)
        parts = validated_data.get('parts', None)
        if parts is None:
            raise ValidationError({'parts': _("Missing required field")}, code='missing')
        if len(parts) > asset_upload.number_parts:
            raise ValidationError({'parts': [_("Too many parts")]}, code='invalid')
        if len(parts) < asset_upload.number_parts:
            raise ValidationError({'parts': [_("Too few parts")]}, code='invalid')
        executor.complete_multipart_upload(key, asset, parts, asset_upload.upload_id)
        asset_upload.update_asset_checksum_multihash()
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
