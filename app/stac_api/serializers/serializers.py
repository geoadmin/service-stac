import logging
from collections import OrderedDict
from urllib.parse import urlparse

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict
from rest_framework.validators import UniqueValidator

from stac_api.models import AssetUpload
from stac_api.models import CollectionAssetUpload
from stac_api.models import LandingPage
from stac_api.models import LandingPageLink
from stac_api.serializers.serializers_utils import DictSerializer
from stac_api.serializers.serializers_utils import NonNullModelSerializer
from stac_api.utils import build_asset_href
from stac_api.utils import get_browser_url
from stac_api.utils import get_stac_version
from stac_api.utils import get_url
from stac_api.utils import is_api_version_1
from stac_api.utils import isoformat
from stac_api.validators import validate_checksum_multihash_sha256
from stac_api.validators import validate_content_encoding
from stac_api.validators import validate_md5_parts
from stac_api.validators import validate_name

logger = logging.getLogger(__name__)


class LandingPageLinkSerializer(serializers.ModelSerializer):

    class Meta:
        model = LandingPageLink
        fields = ['href', 'rel', 'link_type', 'title']


class ConformancePageSerializer(serializers.ModelSerializer):

    class Meta:
        model = LandingPage
        fields = ['conformsTo']


class LandingPageSerializer(serializers.ModelSerializer):

    class Meta:
        model = LandingPage
        fields = ['id', 'title', 'description', 'links', 'stac_version', 'conformsTo']

    # NOTE: when explicitely declaring fields, we need to add the validation as for the field
    # in model !
    id = serializers.CharField(
        max_length=255,
        source="name",
        validators=[validate_name, UniqueValidator(queryset=LandingPage.objects.all())]
    )
    # Read only fields
    links = LandingPageLinkSerializer(many=True, read_only=True)
    stac_version = serializers.SerializerMethodField()

    def get_stac_version(self, obj):
        return get_stac_version(self.context.get('request'))

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get("request")

        # Add hardcoded value Catalog to response to conform to stac spec v1.
        representation['type'] = "Catalog"

        # Remove property on older versions
        if not is_api_version_1(request):
            del representation['type']

        version = request.resolver_match.namespace
        spec_base = f'{urlparse(settings.STATIC_SPEC_URL).path.strip(' / ')}/{version}'
        # Add auto links
        # We use OrderedDict, although it is not necessary, because the default serializer/model for
        # links already uses OrderedDict, this way we keep consistency between auto link and user
        # link
        representation['links'][:0] = [
            OrderedDict([
                ('rel', 'root'),
                ('href', get_url(request, 'landing-page')),
                ("type", "application/json"),
            ]),
            OrderedDict([
                ('rel', 'self'),
                ('href', get_url(request, 'landing-page')),
                ("type", "application/json"),
                ("title", "This document"),
            ]),
            OrderedDict([
                ("rel", "service-doc"),
                ("href", request.build_absolute_uri(f"/{spec_base}/api.html")),
                ("type", "text/html"),
                ("title", "The API documentation"),
            ]),
            OrderedDict([
                ("rel", "service-desc"),
                ("href", request.build_absolute_uri(f"/{spec_base}/openapi.yaml")),
                ("type", "application/vnd.oai.openapi+yaml;version=3.0"),
                ("title", "The OPENAPI description of the service"),
            ]),
            OrderedDict([
                ("rel", "conformance"),
                ("href", get_url(request, 'conformance')),
                ("type", "application/json"),
                ("title", "OGC API conformance classes implemented by this server"),
            ]),
            OrderedDict([
                ('rel', 'data'),
                ('href', get_url(request, 'collections-list')),
                ("type", "application/json"),
                ("title", "Information about the feature collections"),
            ]),
            OrderedDict([
                ("href", get_url(request, 'search-list')),
                ("rel", "search"),
                ("method", "GET"),
                ("type", "application/json"),
                ("title", "Search across feature collections"),
            ]),
            OrderedDict([
                ("href", get_url(request, 'search-list')),
                ("rel", "search"),
                ("method", "POST"),
                ("type", "application/json"),
                ("title", "Search across feature collections"),
            ]),
            OrderedDict([
                ("href", get_browser_url(request, 'browser-catalog')),
                ("rel", "alternate"),
                ("type", "text/html"),
                ("title", "STAC Browser"),
            ]),
        ]
        return representation


class AssetsDictSerializer(DictSerializer):
    '''Assets serializer list to dictionary

    This serializer returns an asset dictionary with the asset name as keys.
    '''
    # pylint: disable=abstract-method
    key_identifier = 'id'


class HrefField(serializers.Field):
    '''Special Href field for Assets'''

    # pylint: disable=abstract-method

    def to_representation(self, value):
        # build an absolute URL from the file path
        request = self.context.get("request")
        path = value.name

        if value.instance.is_external:
            return path
        return build_asset_href(request, path)

    def to_internal_value(self, data):
        return data


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
