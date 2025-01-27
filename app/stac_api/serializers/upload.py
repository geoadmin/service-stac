import logging

from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict

from stac_api.models.general import AssetUpload
from stac_api.models.general import CollectionAssetUpload
from stac_api.serializers.utils import NonNullModelSerializer
from stac_api.utils import is_api_version_1
from stac_api.utils import isoformat
from stac_api.validators import validate_checksum_multihash_sha256
from stac_api.validators import validate_content_encoding
from stac_api.validators import validate_md5_parts

logger = logging.getLogger(__name__)


class AssetUploadListSerializer(serializers.ListSerializer):
    # pylint: disable=abstract-method

    def to_representation(self, data):
        return {'uploads': super().to_representation(data)}

    @property
    def data(self):
        ret = super(serializers.ListSerializer, self).data
        return ReturnDict(ret, serializer=self)


class UploadPartSerializer(serializers.Serializer):
    '''This serializer is used to serialize the data from/to the S3 API.
    '''
    # pylint: disable=abstract-method
    etag = serializers.CharField(source='ETag', allow_blank=False, required=True)
    part_number = serializers.IntegerField(
        source='PartNumber', min_value=1, max_value=100, required=True, allow_null=False
    )
    modified = serializers.DateTimeField(source='LastModified', required=False, allow_null=True)
    size = serializers.IntegerField(source='Size', allow_null=True, required=False)


class AssetUploadSerializer(NonNullModelSerializer):

    class Meta:
        model = AssetUpload
        list_serializer_class = AssetUploadListSerializer
        fields = [
            'upload_id',
            'status',
            'created',
            'checksum_multihash',
            'completed',
            'aborted',
            'number_parts',
            'md5_parts',
            'urls',
            'ended',
            'parts',
            'update_interval',
            'content_encoding'
        ]

    checksum_multihash = serializers.CharField(
        source='checksum_multihash',
        max_length=255,
        required=True,
        allow_blank=False,
        validators=[validate_checksum_multihash_sha256]
    )
    md5_parts = serializers.JSONField(required=True)
    update_interval = serializers.IntegerField(
        required=False, allow_null=False, min_value=-1, max_value=3600, default=-1
    )
    content_encoding = serializers.CharField(
        required=False,
        allow_null=False,
        allow_blank=False,
        min_length=1,
        max_length=32,
        default='',
        validators=[validate_content_encoding]
    )

    # write only fields
    ended = serializers.DateTimeField(write_only=True, required=False)
    parts = serializers.ListField(
        child=UploadPartSerializer(), write_only=True, allow_empty=False, required=False
    )

    # Read only fields
    upload_id = serializers.CharField(read_only=True)
    created = serializers.DateTimeField(read_only=True)
    urls = serializers.JSONField(read_only=True)
    completed = serializers.SerializerMethodField()
    aborted = serializers.SerializerMethodField()

    def validate(self, attrs):
        # get partial from kwargs (if partial true and no md5 : ok, if false no md5 : error)
        # Check the md5 parts length
        if attrs.get('md5_parts') is not None:
            validate_md5_parts(attrs['md5_parts'], attrs['number_parts'])
        elif not self.partial:
            raise serializers.ValidationError(
                detail={'md5_parts': _('md5_parts parameter is missing')}, code='missing'
            )
        return attrs

    def get_completed(self, obj):
        if obj.status == AssetUpload.Status.COMPLETED:
            return isoformat(obj.ended)
        return None

    def get_aborted(self, obj):
        if obj.status == AssetUpload.Status.ABORTED:
            return isoformat(obj.ended)
        return None

    def get_fields(self):
        fields = super().get_fields()
        # This is a hack to allow fields with special characters
        fields['file:checksum'] = fields.pop('checksum_multihash')

        # Older versions of the api still use different name
        request = self.context.get('request')
        if not is_api_version_1(request):
            fields['checksum:multihash'] = fields.pop('file:checksum')
        return fields


class AssetUploadPartsSerializer(serializers.Serializer):
    '''S3 list_parts response serializer'''

    # pylint: disable=abstract-method

    class Meta:
        list_serializer_class = AssetUploadListSerializer

    # Read only fields
    parts = serializers.ListField(
        source='Parts', child=UploadPartSerializer(), default=list, read_only=True
    )


class CollectionAssetUploadSerializer(NonNullModelSerializer):

    class Meta:
        model = CollectionAssetUpload
        list_serializer_class = AssetUploadListSerializer
        fields = [
            'upload_id',
            'status',
            'created',
            'checksum_multihash',
            'completed',
            'aborted',
            'number_parts',
            'md5_parts',
            'urls',
            'ended',
            'parts',
            'update_interval',
            'content_encoding'
        ]

    checksum_multihash = serializers.CharField(
        source='checksum_multihash',
        max_length=255,
        required=True,
        allow_blank=False,
        validators=[validate_checksum_multihash_sha256]
    )
    md5_parts = serializers.JSONField(required=True)
    update_interval = serializers.IntegerField(
        required=False, allow_null=False, min_value=-1, max_value=3600, default=-1
    )
    content_encoding = serializers.CharField(
        required=False,
        allow_null=False,
        allow_blank=False,
        min_length=1,
        max_length=32,
        default='',
        validators=[validate_content_encoding]
    )

    # write only fields
    ended = serializers.DateTimeField(write_only=True, required=False)
    parts = serializers.ListField(
        child=UploadPartSerializer(), write_only=True, allow_empty=False, required=False
    )

    # Read only fields
    upload_id = serializers.CharField(read_only=True)
    created = serializers.DateTimeField(read_only=True)
    urls = serializers.JSONField(read_only=True)
    completed = serializers.SerializerMethodField()
    aborted = serializers.SerializerMethodField()

    def validate(self, attrs):
        # get partial from kwargs (if partial true and no md5 : ok, if false no md5 : error)
        # Check the md5 parts length
        if attrs.get('md5_parts') is not None:
            validate_md5_parts(attrs['md5_parts'], attrs['number_parts'])
        elif not self.partial:
            raise serializers.ValidationError(
                detail={'md5_parts': _('md5_parts parameter is missing')}, code='missing'
            )
        return attrs

    def get_completed(self, obj):
        if obj.status == CollectionAssetUpload.Status.COMPLETED:
            return isoformat(obj.ended)
        return None

    def get_aborted(self, obj):
        if obj.status == CollectionAssetUpload.Status.ABORTED:
            return isoformat(obj.ended)
        return None

    def get_fields(self):
        fields = super().get_fields()
        # This is a hack to allow fields with special characters
        fields['file:checksum'] = fields.pop('checksum_multihash')

        # Older versions of the api still use different name
        request = self.context.get('request')
        if not is_api_version_1(request):
            fields['checksum:multihash'] = fields.pop('file:checksum')
        return fields
