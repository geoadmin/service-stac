import hashlib
import base64
import logging
from datetime import datetime
from operator import itemgetter

from django.db import IntegrityError
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.test import Client

from rest_framework import generics
from rest_framework import mixins
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework_condition import etag

from stac_api.exceptions import UploadInProgressError
from stac_api.exceptions import UploadNotInProgressError
from stac_api.models.collection import CollectionAsset
from stac_api.models.collection import CollectionAssetUpload
from stac_api.models.general import BaseAssetUpload
from stac_api.models.item import Asset
from stac_api.models.item import AssetUpload
from stac_api.pagination import ExtApiPagination
from stac_api.s3_multipart_upload import MultipartUpload
from stac_api.serializers.upload import AssetUploadPartsSerializer
from stac_api.serializers.upload import AssetUploadSerializer
from stac_api.serializers.upload import CollectionAssetUploadSerializer
from stac_api.utils import compute_md5_base64, get_asset_path
from stac_api.utils import get_collection_asset_path
from stac_api.utils import select_s3_bucket
from stac_api.utils import utc_aware
from stac_api.validators_view import validate_asset
from stac_api.validators_view import validate_collection_asset
from stac_api.views.general import get_etag
from stac_api.views.mixins import CreateModelMixin
from stac_api.views.mixins import DestroyModelMixin
from stac_api.views.mixins import UpdateInsertModelMixin
from tests.tests_09.test_asset_upload_endpoint import AssetUploadBaseTest
from tests.tests_09.utils import reverse_version
from tests.utils import client_login, get_file_like_object

logger = logging.getLogger(__name__)


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

    def create_multipart_upload(self, executor, serializer, validated_data, asset, key=None):
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

    def create_multipart_upload_2(self, executor, serializer, validated_data, asset, key):

        upload_id = executor.create_multipart_upload(
            key,
            asset,
            validated_data['checksum_multihash'],
            validated_data['update_interval'],
            validated_data['content_encoding']
        )
        urls = []
        sorted_md5_parts = sorted(validated_data['md5_parts'], key=itemgetter('part_number'))
        logger.info(
            f"key for presigned: {key}, asset: {asset}, sorted_md5_parts : {sorted_md5_parts} upload_id: {upload_id}"
        )
        try:
            for part in sorted_md5_parts:
                urls.append(
                    executor.create_presigned_url(
                        key, asset, part['part_number'], upload_id, part['md5']
                    )
                )
            logger.info(f"Presigned URLs: {urls}")
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
        asset_upload.file_size = executor.complete_multipart_upload(
            key, asset, parts, asset_upload.upload_id
        )
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


class AdminAssetUploadHelper(AssetUploadBaseTest):
    """
    This class allows the admin site to use AssetUploadBaseTest's multipart upload methods.
    It acts as a bridge between Django Admin and Django REST framework.
    """

    def __init__(self, request=None):
        self.request = request
        self.key = None
        self.asset = None
        self.item = None
        self.client = Client()
        client_login(self.client)

    def utf8len(self, s):
        return len(s.encode('utf-8'))

    def get_create_multipart_upload_path(self):
        return reverse_version(
            'asset-uploads-list',
            args=[self.asset.item.collection.name, self.asset.item.name, self.asset.name]
        )

    def get_complete_multipart_upload_path(self, upload_id):
        return reverse_version(
            'asset-upload-complete',
            args=[
                self.asset.item.collection.name, self.asset.item.name, self.asset.name, upload_id
            ]
        )

    def admin_create_multipart_upload(self, asset, upload_request_data):
        """
        Admin version of create_multipart_upload.
        Simulates the behavior of a DRF serializer while ensuring that all required fields are included.
        """

        self.key = get_asset_path(asset.item, asset.name)
        self.asset = asset
        self.item = asset.item

        logger.info("Key in admin create multipart upload is %s", self.key)

        md5_parts = [{
            'part_number': 1,
            'md5': compute_md5_base64(upload_request_data.get("file_content", b"mybinarydata2"))
        }]
        response = self.client.post(
            self.get_create_multipart_upload_path(),
            data={
                'number_parts': upload_request_data.get("number_parts", 1),
                'md5_parts': md5_parts,
                'checksum:multihash': upload_request_data.get("file:checksum", "")
            },
            content_type=upload_request_data.get("content_type", "")
        )
        logger.info(f"Response content : {response.content}")
        json_data = response.json()

        return json_data

    def admin_complete_multipart_upload(self, upload_request_data, json_data):
        """
        Admin version of complete_multipart_upload.
        """

        number_parts = 1
        size = len(upload_request_data.get("file_content", b"binary_data"))

        parts = self.s3_upload_parts(
            json_data['upload_id'],
            upload_request_data.get("file_content", b"binary_data"),
            size,
            number_parts
        )
        response = self.client.post(
            self.get_complete_multipart_upload_path(json_data['upload_id']),
            data={'parts': parts},
            content_type=upload_request_data.get("content_type", "")
        )
        logger.info(f"Response content complete upload: {response.content}")
        self.assertStatusCode(200, response)
        self.assertS3ObjectExists(self.key)
        obj = self.get_s3_object(self.key)
        logger.info(f"S3 Object: {obj}")

        return {"message": "Upload completed"}


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


class AssetUploadsList(AssetUploadBase, mixins.ListModelMixin, CreateModelMixin):

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


class AssetUploadDetail(AssetUploadBase, mixins.RetrieveModelMixin, DestroyModelMixin):

    @etag(get_asset_upload_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class AssetUploadComplete(AssetUploadBase, UpdateInsertModelMixin):

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


class AssetUploadAbort(AssetUploadBase, UpdateInsertModelMixin):

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
    CollectionAssetUploadBase, mixins.ListModelMixin, CreateModelMixin
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
    CollectionAssetUploadBase, mixins.RetrieveModelMixin, DestroyModelMixin
):

    @etag(get_collection_asset_upload_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class CollectionAssetUploadComplete(CollectionAssetUploadBase, UpdateInsertModelMixin):

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


class CollectionAssetUploadAbort(CollectionAssetUploadBase, UpdateInsertModelMixin):

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
