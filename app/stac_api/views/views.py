import json
import logging
from datetime import datetime
from operator import itemgetter

from django.conf import settings
from django.db import IntegrityError
from django.db import transaction
from django.db.models import Min
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rest_framework import generics
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.exceptions import APIException
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_condition import etag

from stac_api.exceptions import UploadInProgressError
from stac_api.exceptions import UploadNotInProgressError
from stac_api.models import Asset
from stac_api.models import AssetUpload
from stac_api.models import BaseAssetUpload
from stac_api.models import Collection
from stac_api.models import CollectionAsset
from stac_api.models import CollectionAssetUpload
from stac_api.models import Item
from stac_api.models import LandingPage
from stac_api.pagination import ExtApiPagination
from stac_api.pagination import GetPostCursorPagination
from stac_api.s3_multipart_upload import MultipartUpload
from stac_api.serializers import AssetSerializer
from stac_api.serializers import AssetUploadPartsSerializer
from stac_api.serializers import AssetUploadSerializer
from stac_api.serializers import CollectionAssetSerializer
from stac_api.serializers import CollectionAssetUploadSerializer
from stac_api.serializers import ConformancePageSerializer
from stac_api.serializers import ItemSerializer
from stac_api.serializers import LandingPageSerializer
from stac_api.serializers_utils import get_relation_links
from stac_api.utils import call_calculate_extent
from stac_api.utils import get_asset_path
from stac_api.utils import get_collection_asset_path
from stac_api.utils import harmonize_post_get_for_search
from stac_api.utils import is_api_version_1
from stac_api.utils import select_s3_bucket
from stac_api.utils import utc_aware
from stac_api.validators_serializer import ValidateSearchRequest
from stac_api.validators_view import validate_asset
from stac_api.validators_view import validate_collection
from stac_api.validators_view import validate_collection_asset
from stac_api.validators_view import validate_item
from stac_api.validators_view import validate_renaming
from stac_api.views import views_mixins

logger = logging.getLogger(__name__)


def get_etag(queryset):
    if queryset.exists():
        return list(queryset.only('etag').values('etag').first().values())[0]
    return None


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


def get_collection_asset_upload_etag(request, *args, **kwargs):
    '''Get the ETag for a collection asset upload object

    The ETag is an UUID4 computed on each object changes
    '''
    return get_etag(
        CollectionAssetUpload.objects.filter(
            asset__collection__name=kwargs['collection_name'],
            asset__name=kwargs['asset_name'],
            upload_id=kwargs['upload_id']
        )
    )


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


@api_view(['POST'])
@permission_classes((permissions.AllowAny,))
def recalculate_extent(request):
    call_calculate_extent()
    return Response()


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
        # here. See serialiers.AssetBaseSerializer._validate_href_field
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


class SharedAssetUploadBase(generics.GenericAPIView):
    """SharedAssetUploadBase provides a base view for asset uploads and collection asset uploads.
    """
    lookup_url_kwarg = "upload_id"
    lookup_field = "upload_id"

    def get_queryset(self):
        raise NotImplementedError("get_queryset() not implemented")

    def get_in_progress_queryset(self):
        return self.get_queryset().filter(status=BaseAssetUpload.Status.IN_PROGRESS)

    def get_asset_or_404(self):
        raise NotImplementedError("get_asset_or_404() not implemented")

    def log_extra(self, asset):
        if isinstance(asset, CollectionAsset):
            return {'collection': asset.collection.name, 'asset': asset.name}
        return {
            'collection': asset.item.collection.name, 'item': asset.item.name, 'asset': asset.name
        }

    def get_path(self, asset):
        if isinstance(asset, CollectionAsset):
            return get_collection_asset_path(asset.collection, asset.name)
        return get_asset_path(asset.item, asset.name)

    def _save_asset_upload(self, executor, serializer, key, asset, upload_id, urls):
        try:
            with transaction.atomic():
                serializer.save(asset=asset, upload_id=upload_id, urls=urls)
        except IntegrityError as error:
            logger.error(
                'Failed to create asset upload multipart: %s', error, extra=self.log_extra(asset)
            )
            if bool(self.get_in_progress_queryset()):
                raise UploadInProgressError(
                    data={"upload_id": self.get_in_progress_queryset()[0].upload_id}
                ) from None
            raise

    def create_multipart_upload(self, executor, serializer, validated_data, asset):
        key = self.get_path(asset)

        upload_id = executor.create_multipart_upload(
            key,
            asset,
            validated_data['checksum_multihash'],
            validated_data['update_interval'],
            validated_data['content_encoding']
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
        except APIException as err:
            executor.abort_multipart_upload(key, asset, upload_id)
            raise

    def complete_multipart_upload(self, executor, validated_data, asset_upload, asset):
        key = self.get_path(asset)
        parts = validated_data.get('parts', None)
        if parts is None:
            raise serializers.ValidationError({
                'parts': _("Missing required field")
            }, code='missing')
        if len(parts) > asset_upload.number_parts:
            raise serializers.ValidationError({'parts': [_("Too many parts")]}, code='invalid')
        if len(parts) < asset_upload.number_parts:
            raise serializers.ValidationError({'parts': [_("Too few parts")]}, code='invalid')
        if asset_upload.status != BaseAssetUpload.Status.IN_PROGRESS:
            raise UploadNotInProgressError()
        executor.complete_multipart_upload(key, asset, parts, asset_upload.upload_id)
        asset_upload.update_asset_from_upload()
        asset_upload.status = BaseAssetUpload.Status.COMPLETED
        asset_upload.ended = utc_aware(datetime.utcnow())
        asset_upload.urls = []
        asset_upload.save()

    def abort_multipart_upload(self, executor, asset_upload, asset):
        key = self.get_path(asset)
        executor.abort_multipart_upload(key, asset, asset_upload.upload_id)
        asset_upload.status = BaseAssetUpload.Status.ABORTED
        asset_upload.ended = utc_aware(datetime.utcnow())
        asset_upload.urls = []
        asset_upload.save()

    def list_multipart_upload_parts(self, executor, asset_upload, asset, limit, offset):
        key = self.get_path(asset)
        return executor.list_upload_parts(key, asset, asset_upload.upload_id, limit, offset)


class AssetUploadBase(SharedAssetUploadBase):
    """AssetUploadBase is the base for all asset (not collection asset) upload views.
    """
    serializer_class = AssetUploadSerializer

    def get_queryset(self):
        return AssetUpload.objects.filter(
            asset__item__collection__name=self.kwargs['collection_name'],
            asset__item__name=self.kwargs['item_name'],
            asset__name=self.kwargs['asset_name']
        ).prefetch_related('asset')

    def get_asset_or_404(self):
        return get_object_or_404(
            Asset.objects.all(),
            name=self.kwargs['asset_name'],
            item__name=self.kwargs['item_name'],
            item__collection__name=self.kwargs['collection_name']
        )


class AssetUploadsList(AssetUploadBase, mixins.ListModelMixin, views_mixins.CreateModelMixin):

    class ExternalDisallowedException(Exception):
        pass

    def post(self, request, *args, **kwargs):
        try:
            return self.create(request, *args, **kwargs)
        except self.ExternalDisallowedException as ex:
            data = {
                "code": 400,
                "description": "Not allowed to create multipart uploads on external assets"
            }
            return Response(status=400, exception=True, data=data)

    def get(self, request, *args, **kwargs):
        validate_asset(self.kwargs)
        return self.list(request, *args, **kwargs)

    def get_success_headers(self, data):
        return {'Location': '/'.join([self.request.build_absolute_uri(), data['upload_id']])}

    def perform_create(self, serializer):
        data = serializer.validated_data
        asset = self.get_asset_or_404()
        collection = asset.item.collection

        if asset.is_external:
            raise self.ExternalDisallowedException()

        s3_bucket = select_s3_bucket(collection.name)
        executor = MultipartUpload(s3_bucket)

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


class AssetUploadComplete(AssetUploadBase, views_mixins.UpdateInsertModelMixin):

    def post(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def perform_update(self, serializer):
        asset = serializer.instance.asset

        collection = asset.item.collection

        s3_bucket = select_s3_bucket(collection.name)
        executor = MultipartUpload(s3_bucket)

        self.complete_multipart_upload(
            executor, serializer.validated_data, serializer.instance, asset
        )


class AssetUploadAbort(AssetUploadBase, views_mixins.UpdateInsertModelMixin):

    def post(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def perform_update(self, serializer):
        asset = serializer.instance.asset

        collection = asset.item.collection

        s3_bucket = select_s3_bucket(collection.name)
        executor = MultipartUpload(s3_bucket)
        self.abort_multipart_upload(executor, serializer.instance, asset)


class AssetUploadPartsList(AssetUploadBase):
    serializer_class = AssetUploadPartsSerializer
    pagination_class = ExtApiPagination

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        asset_upload = self.get_object()
        limit, offset = self.get_pagination_config(request)

        collection = asset_upload.asset.item.collection
        s3_bucket = select_s3_bucket(collection.name)

        executor = MultipartUpload(s3_bucket)

        data, has_next = self.list_multipart_upload_parts(
            executor, asset_upload, asset_upload.asset, limit, offset
        )
        serializer = self.get_serializer(data)

        return self.get_paginated_response(serializer.data, has_next)

    def get_pagination_config(self, request):
        return self.paginator.get_pagination_config(request)

    def get_paginated_response(self, data, has_next):  # pylint: disable=arguments-differ
        return self.paginator.get_paginated_response(data, has_next)


class CollectionAssetUploadBase(SharedAssetUploadBase):
    """CollectionAssetUploadBase is the base for all collection asset upload views.
    """
    serializer_class = CollectionAssetUploadSerializer

    def get_queryset(self):
        return CollectionAssetUpload.objects.filter(
            asset__collection__name=self.kwargs['collection_name'],
            asset__name=self.kwargs['asset_name']
        ).prefetch_related('asset')

    def get_asset_or_404(self):
        return get_object_or_404(
            CollectionAsset.objects.all(),
            name=self.kwargs['asset_name'],
            collection__name=self.kwargs['collection_name']
        )


class CollectionAssetUploadsList(
    CollectionAssetUploadBase, mixins.ListModelMixin, views_mixins.CreateModelMixin
):

    class ExternalDisallowedException(Exception):
        pass

    def post(self, request, *args, **kwargs):
        try:
            return self.create(request, *args, **kwargs)
        except self.ExternalDisallowedException as ex:
            data = {
                "code": 400,
                "description": "Not allowed to create multipart uploads on external assets"
            }
            return Response(status=400, exception=True, data=data)

    def get(self, request, *args, **kwargs):
        validate_collection_asset(self.kwargs)
        return self.list(request, *args, **kwargs)

    def get_success_headers(self, data):
        return {'Location': '/'.join([self.request.build_absolute_uri(), data['upload_id']])}

    def perform_create(self, serializer):
        data = serializer.validated_data
        asset = self.get_asset_or_404()
        collection = asset.collection

        if asset.is_external:
            raise self.ExternalDisallowedException()

        s3_bucket = select_s3_bucket(collection.name)
        executor = MultipartUpload(s3_bucket)

        self.create_multipart_upload(executor, serializer, data, asset)

    def get_queryset(self):
        queryset = super().get_queryset()

        status = self.request.query_params.get('status', None)
        if status:
            queryset = queryset.filter_by_status(status)

        return queryset


class CollectionAssetUploadDetail(
    CollectionAssetUploadBase, mixins.RetrieveModelMixin, views_mixins.DestroyModelMixin
):

    @etag(get_collection_asset_upload_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class CollectionAssetUploadComplete(CollectionAssetUploadBase, views_mixins.UpdateInsertModelMixin):

    def post(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def perform_update(self, serializer):
        asset = serializer.instance.asset

        collection = asset.collection

        s3_bucket = select_s3_bucket(collection.name)
        executor = MultipartUpload(s3_bucket)

        self.complete_multipart_upload(
            executor, serializer.validated_data, serializer.instance, asset
        )


class CollectionAssetUploadAbort(CollectionAssetUploadBase, views_mixins.UpdateInsertModelMixin):

    def post(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def perform_update(self, serializer):
        asset = serializer.instance.asset

        collection = asset.collection

        s3_bucket = select_s3_bucket(collection.name)
        executor = MultipartUpload(s3_bucket)
        self.abort_multipart_upload(executor, serializer.instance, asset)


class CollectionAssetUploadPartsList(CollectionAssetUploadBase):
    serializer_class = AssetUploadPartsSerializer
    pagination_class = ExtApiPagination

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        asset_upload = self.get_object()
        limit, offset = self.get_pagination_config(request)

        collection = asset_upload.asset.collection
        s3_bucket = select_s3_bucket(collection.name)

        executor = MultipartUpload(s3_bucket)

        data, has_next = self.list_multipart_upload_parts(
            executor, asset_upload, asset_upload.asset, limit, offset
        )
        serializer = self.get_serializer(data)

        return self.get_paginated_response(serializer.data, has_next)

    def get_pagination_config(self, request):
        return self.paginator.get_pagination_config(request)

    def get_paginated_response(self, data, has_next):  # pylint: disable=arguments-differ
        return self.paginator.get_paginated_response(data, has_next)