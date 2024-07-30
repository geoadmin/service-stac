import logging
from collections import OrderedDict
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError as CoreValidationError
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict
from rest_framework.validators import UniqueValidator
from rest_framework_gis import serializers as gis_serializers

from stac_api.models import Asset
from stac_api.models import AssetUpload
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import LandingPage
from stac_api.models import LandingPageLink
from stac_api.models import Provider
from stac_api.serializers_utils import DictSerializer
from stac_api.serializers_utils import NonNullModelSerializer
from stac_api.serializers_utils import UpsertModelSerializerMixin
from stac_api.serializers_utils import get_relation_links
from stac_api.serializers_utils import update_or_create_links
from stac_api.utils import build_asset_href
from stac_api.utils import get_browser_url
from stac_api.utils import get_stac_version
from stac_api.utils import get_url
from stac_api.utils import is_api_version_1
from stac_api.utils import isoformat
from stac_api.validators import normalize_and_validate_media_type
from stac_api.validators import validate_asset_name
from stac_api.validators import validate_asset_name_with_media_type
from stac_api.validators import validate_checksum_multihash_sha256
from stac_api.validators import validate_content_encoding
from stac_api.validators import validate_geoadmin_variant
from stac_api.validators import validate_href_url
from stac_api.validators import validate_item_properties_datetimes
from stac_api.validators import validate_md5_parts
from stac_api.validators import validate_name
from stac_api.validators_serializer import validate_json_payload
from stac_api.validators_serializer import validate_uniqueness_and_create

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


class ProviderSerializer(NonNullModelSerializer):

    class Meta:
        model = Provider
        fields = ['name', 'roles', 'url', 'description']


class CollectionLinkSerializer(NonNullModelSerializer):

    class Meta:
        model = CollectionLink
        fields = ['href', 'rel', 'title', 'type']

    # NOTE: when explicitely declaring fields, we need to add the validation as for the field
    # in model !
    type = serializers.CharField(
        required=False, allow_blank=True, max_length=150, source="link_type"
    )


class ItemLinkSerializer(NonNullModelSerializer):

    class Meta:
        model = ItemLink
        fields = ['href', 'rel', 'title', 'type']

    # NOTE: when explicitely declaring fields, we need to add the validation as for the field
    # in model !
    type = serializers.CharField(
        required=False, allow_blank=True, max_length=255, source="link_type"
    )


class ItemsPropertiesSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    # ItemsPropertiesSerializer is a nested serializer and don't directly create/write instances
    # therefore we don't need to implement the super method create() and update()

    # NOTE: when explicitely declaring fields, we need to add the validation as for the field
    # in model !
    datetime = serializers.DateTimeField(source='properties_datetime', required=False, default=None)
    start_datetime = serializers.DateTimeField(
        source='properties_start_datetime', required=False, default=None
    )
    end_datetime = serializers.DateTimeField(
        source='properties_end_datetime', required=False, default=None
    )
    title = serializers.CharField(
        source='properties_title',
        required=False,
        allow_blank=False,
        allow_null=True,
        max_length=255,
        default=None
    )
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)


class BboxSerializer(gis_serializers.GeoFeatureModelSerializer):

    class Meta:
        model = Item
        geo_field = "geometry"
        auto_bbox = True
        fields = ['geometry']

    def to_representation(self, instance):
        python_native = super().to_representation(instance)
        return python_native['bbox']


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


class AssetBaseSerializer(NonNullModelSerializer, UpsertModelSerializerMixin):
    '''Asset serializer base class
    '''

    class Meta:
        model = Asset
        fields = [
            'id',
            'title',
            'type',
            'href',
            'description',
            'eo_gsd',
            'roles',
            'geoadmin_lang',
            'geoadmin_variant',
            'proj_epsg',
            'checksum_multihash',
            'created',
            'updated',
        ]
        validators = []  # Remove a default "unique together" constraint.
        # (see:
        # https://www.django-rest-framework.org/api-guide/validators/#limitations-of-validators)

    # NOTE: when explicitely declaring fields, we need to add the validation as for the field
    # in model !
    id = serializers.CharField(source='name', max_length=255, validators=[validate_asset_name])
    title = serializers.CharField(
        required=False, max_length=255, allow_null=True, allow_blank=False
    )
    description = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    # Can't be a ChoiceField, as the validate method normalizes the MIME string only after it
    # is read. Consistency is nevertheless guaranteed by the validate() and validate_type() methods.
    type = serializers.CharField(
        source='media_type', required=True, allow_null=False, allow_blank=False
    )
    # Here we need to explicitely define these fields with the source, because they are renamed
    # in the get_fields() method
    eo_gsd = serializers.FloatField(source='eo_gsd', required=False, allow_null=True)
    geoadmin_lang = serializers.ChoiceField(
        source='geoadmin_lang',
        choices=Asset.Language.values,
        required=False,
        allow_null=True,
        allow_blank=False
    )
    geoadmin_variant = serializers.CharField(
        source='geoadmin_variant',
        max_length=25,
        allow_blank=False,
        allow_null=True,
        required=False,
        validators=[validate_geoadmin_variant]
    )
    proj_epsg = serializers.IntegerField(source='proj_epsg', allow_null=True, required=False)
    # read only fields
    checksum_multihash = serializers.CharField(source='checksum_multihash', read_only=True)
    href = HrefField(source='file', required=False)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)

    # helper variable to provide the collection for upsert validation
    # see views.AssetDetail.perform_upsert
    collection = None

    def create(self, validated_data):
        asset = validate_uniqueness_and_create(Asset, validated_data)
        return asset

    def update_or_create(self, look_up, validated_data):
        """
        Update or create the asset object selected by kwargs and return the instance.
        When no asset object matching the kwargs selection, a new asset is created.
        Args:
            validated_data: dict
                Copy of the validated_data to use for update
            kwargs: dict
                Object selection arguments (NOTE: the selection arguments must match a unique
                object in DB otherwise an IntegrityError will be raised)
        Returns: tuple
            Asset instance and True if created otherwise false
        """
        asset, created = Asset.objects.update_or_create(**look_up, defaults=validated_data)
        return asset, created

    def validate_type(self, value):
        ''' Validates the the field "type"
        '''
        return normalize_and_validate_media_type(value)

    def validate(self, attrs):
        name = attrs['name'] if not self.partial else attrs.get('name', self.instance.name)
        media_type = attrs['media_type'] if not self.partial else attrs.get(
            'media_type', self.instance.media_type
        )
        validate_asset_name_with_media_type(name, media_type)

        validate_json_payload(self)

        return attrs

    def get_fields(self):
        fields = super().get_fields()
        # This is a hack to allow fields with special characters
        fields['gsd'] = fields.pop('eo_gsd')
        fields['proj:epsg'] = fields.pop('proj_epsg')
        fields['geoadmin:variant'] = fields.pop('geoadmin_variant')
        fields['geoadmin:lang'] = fields.pop('geoadmin_lang')
        fields['file:checksum'] = fields.pop('checksum_multihash')

        # Older versions of the api still use different name
        request = self.context.get('request')
        if not is_api_version_1(request):
            fields['checksum:multihash'] = fields.pop('file:checksum')
            fields['eo:gsd'] = fields.pop('gsd')
            fields.pop('roles', None)

        return fields


class AssetSerializer(AssetBaseSerializer):
    '''Asset serializer for the asset views

    This serializer adds the links list attribute.
    '''

    def to_representation(self, instance):
        collection = instance.item.collection.name
        item = instance.item.name
        name = instance.name
        request = self.context.get("request")
        representation = super().to_representation(instance)
        # Add auto links
        # We use OrderedDict, although it is not necessary, because the default serializer/model for
        # links already uses OrderedDict, this way we keep consistency between auto link and user
        # link
        representation['links'] = get_relation_links(
            request, 'asset-detail', [collection, item, name]
        )
        return representation

    def _validate_href_field(self, attrs):
        """Only allow the href field if the collection allows for external assets

        Raise an exception, this replicates the previous behaviour when href
        was always read_only
        """
        # the href field is translated to the file field here
        if 'file' in attrs:
            if self.collection:
                collection = self.collection
            else:
                raise Exception("Implementation error")

            if not collection.allow_external_assets:
                logger.info(
                    'Attempted external asset upload with no permission',
                    extra={
                        'collection': self.collection, 'attrs': attrs
                    }
                )
                errors = {'href': _("Found read-only property in payload")}
                raise serializers.ValidationError(code="payload", detail=errors)

            try:
                validate_href_url(attrs['file'], collection)
            except CoreValidationError as e:
                errors = {'href': e.message}
                raise serializers.ValidationError(code='payload', detail=errors)

    def validate(self, attrs):
        self._validate_href_field(attrs)
        return super().validate(attrs)


class AssetsForItemSerializer(AssetBaseSerializer):
    '''Assets serializer for nesting them inside the item

    Assets should be nested inside their item but using a dictionary instead of a list and without
    links.
    '''

    class Meta:
        model = Asset
        list_serializer_class = AssetsDictSerializer
        fields = [
            'id',
            'title',
            'type',
            'href',
            'description',
            'roles',
            'eo_gsd',
            'geoadmin_lang',
            'geoadmin_variant',
            'proj_epsg',
            'checksum_multihash',
            'created',
            'updated'
        ]


class CollectionSerializer(NonNullModelSerializer, UpsertModelSerializerMixin):

    class Meta:
        model = Collection
        fields = [
            'published',
            'stac_version',
            'stac_extensions',
            'id',
            'title',
            'description',
            'summaries',
            'extent',
            'providers',
            'license',
            'created',
            'updated',
            'links',
            'crs',
            'itemType',
            'assets'
        ]
        # crs not in sample data, but in specs..
        validators = []  # Remove a default "unique together" constraint.
        # (see:
        # https://www.django-rest-framework.org/api-guide/validators/#limitations-of-validators)

    published = serializers.BooleanField(write_only=True, default=True)
    # NOTE: when explicitely declaring fields, we need to add the validation as for the field
    # in model !
    id = serializers.CharField(
        required=True, max_length=255, source="name", validators=[validate_name]
    )
    title = serializers.CharField(required=False, allow_blank=False, default=None, max_length=255)
    # Also links are required in the spec, the main links (self, root, items) are automatically
    # generated hence here it is set to required=False which allows to add optional links that
    # are not generated
    links = CollectionLinkSerializer(required=False, many=True)
    providers = ProviderSerializer(required=False, many=True)

    # read only fields
    crs = serializers.SerializerMethodField(read_only=True)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)
    extent = serializers.SerializerMethodField(read_only=True)
    summaries = serializers.SerializerMethodField(read_only=True)
    stac_extensions = serializers.SerializerMethodField(read_only=True)
    stac_version = serializers.SerializerMethodField(read_only=True)
    itemType = serializers.ReadOnlyField(default="Feature")  # pylint: disable=invalid-name
    assets = AssetsForItemSerializer(many=True, read_only=True)

    def get_crs(self, obj):
        return ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"]

    def get_stac_extensions(self, obj):
        return []

    def get_stac_version(self, obj):
        return get_stac_version(self.context.get('request'))

    def get_summaries(self, obj):
        # Older versions of the api still use different name
        request = self.context.get('request')
        if not is_api_version_1(request):
            return {
                'proj:epsg': obj.summaries_proj_epsg or [],
                'eo:gsd': obj.summaries_eo_gsd or [],
                'geoadmin:variant': obj.summaries_geoadmin_variant or [],
                'geoadmin:lang': obj.summaries_geoadmin_lang or []
            }
        return {
            'proj:epsg': obj.summaries_proj_epsg or [],
            'gsd': obj.summaries_eo_gsd or [],
            'geoadmin:variant': obj.summaries_geoadmin_variant or [],
            'geoadmin:lang': obj.summaries_geoadmin_lang or []
        }

    def get_extent(self, obj):
        start = obj.extent_start_datetime
        end = obj.extent_end_datetime
        if start is not None:
            start = isoformat(start)
        if end is not None:
            end = isoformat(end)

        bbox = [0, 0, 0, 0]
        if obj.extent_geometry is not None:
            bbox = list(GEOSGeometry(obj.extent_geometry).extent)

        return {
            "spatial": {
                "bbox": [bbox]
            },
            "temporal": {
                "interval": [[start, end]]
            },
        }

    def _update_or_create_providers(self, collection, providers_data):
        provider_ids = []
        for provider_data in providers_data:
            provider, created = Provider.objects.get_or_create(
                collection=collection,
                name=provider_data["name"],
                defaults={
                    'description': provider_data.get('description', None),
                    'roles': provider_data.get('roles', None),
                    'url': provider_data.get('url', None)
                }
            )
            logger.debug(
                '%s provider %s',
                'created' if created else 'updated',
                provider.name,
                extra={"provider": provider_data}
            )
            provider_ids.append(provider.id)
            # the duplicate here is necessary to update the values in
            # case the object already exists
            provider.description = provider_data.get('description', provider.description)
            provider.roles = provider_data.get('roles', provider.roles)
            provider.url = provider_data.get('url', provider.url)
            provider.full_clean()
            provider.save()

        # Delete providers that were not mentioned in the payload anymore
        deleted = Provider.objects.filter(collection=collection).exclude(id__in=provider_ids
                                                                        ).delete()
        logger.info(
            "deleted %d stale providers for collection %s",
            deleted[0],
            collection.name,
            extra={"collection": collection.name}
        )

    def create(self, validated_data):
        """
        Create and return a new `Collection` instance, given the validated data.
        """
        providers_data = validated_data.pop('providers', [])
        links_data = validated_data.pop('links', [])
        collection = validate_uniqueness_and_create(Collection, validated_data)
        self._update_or_create_providers(collection=collection, providers_data=providers_data)
        update_or_create_links(
            instance_type="collection",
            model=CollectionLink,
            instance=collection,
            links_data=links_data
        )
        return collection

    def update(self, instance, validated_data):
        """
        Update and return an existing `Collection` instance, given the validated data.
        """
        providers_data = validated_data.pop('providers', [])
        links_data = validated_data.pop('links', [])
        self._update_or_create_providers(collection=instance, providers_data=providers_data)
        update_or_create_links(
            instance_type="collection",
            model=CollectionLink,
            instance=instance,
            links_data=links_data
        )
        return super().update(instance, validated_data)

    def update_or_create(self, look_up, validated_data):
        """
        Update or create the collection object selected by kwargs and return the instance.

        When no collection object matching the kwargs selection, a new object is created.

        Args:
            validated_data: dict
                Copy of the validated_data to use for update
            kwargs: dict
                Object selection arguments (NOTE: the selection arguments must match a unique
                object in DB otherwise an IntegrityError will be raised)

        Returns: tuple
            Collection instance and True if created otherwise false
        """
        providers_data = validated_data.pop('providers', [])
        links_data = validated_data.pop('links', [])
        collection, created = Collection.objects.update_or_create(
            **look_up, defaults=validated_data
            )
        self._update_or_create_providers(collection=collection, providers_data=providers_data)
        update_or_create_links(
            instance_type="collection",
            model=CollectionLink,
            instance=collection,
            links_data=links_data
        )
        return collection, created

    def to_representation(self, instance):
        name = instance.name
        request = self.context.get("request")
        representation = super().to_representation(instance)

        # Add hardcoded value Collection to response to conform to stac spec v1.
        representation['type'] = "Collection"

        # Remove property on older versions
        if not is_api_version_1(request):
            del representation['type']

        # Add auto links
        # We use OrderedDict, although it is not necessary, because the default serializer/model for
        # links already uses OrderedDict, this way we keep consistency between auto link and user
        # link
        representation['links'][:0] = get_relation_links(request, 'collection-detail', [name])
        return representation

    def validate(self, attrs):
        validate_json_payload(self)
        return attrs


class ItemSerializer(NonNullModelSerializer, UpsertModelSerializerMixin):

    class Meta:
        model = Item
        fields = [
            'id',
            'collection',
            'type',
            'stac_version',
            'geometry',
            'bbox',
            'properties',
            'stac_extensions',
            'links',
            'assets'
        ]
        validators = []  # Remove a default "unique together" constraint.
        # (see:
        # https://www.django-rest-framework.org/api-guide/validators/#limitations-of-validators)

    # NOTE: when explicitely declaring fields, we need to add the validation as for the field
    # in model !
    id = serializers.CharField(
        source='name', required=True, max_length=255, validators=[validate_name]
    )
    properties = ItemsPropertiesSerializer(source='*', required=True)
    geometry = gis_serializers.GeometryField(required=True)
    links = ItemLinkSerializer(required=False, many=True)
    # read only fields
    type = serializers.SerializerMethodField()
    collection = serializers.SlugRelatedField(slug_field='name', read_only=True)
    bbox = BboxSerializer(source='*', read_only=True)
    assets = AssetsForItemSerializer(many=True, read_only=True)
    stac_extensions = serializers.SerializerMethodField()
    stac_version = serializers.SerializerMethodField()

    def get_type(self, obj):
        return 'Feature'

    def get_stac_extensions(self, obj):
        return []

    def get_stac_version(self, obj):
        return get_stac_version(self.context.get('request'))

    def to_representation(self, instance):
        collection = instance.collection.name
        name = instance.name
        request = self.context.get("request")
        representation = super().to_representation(instance)
        # Add auto links
        # We use OrderedDict, although it is not necessary, because the default serializer/model for
        # links already uses OrderedDict, this way we keep consistency between auto link and user
        # link
        representation['links'][:0] = get_relation_links(request, 'item-detail', [collection, name])
        return representation

    def create(self, validated_data):
        links_data = validated_data.pop('links', [])
        item = validate_uniqueness_and_create(Item, validated_data)
        update_or_create_links(
            instance_type="item", model=ItemLink, instance=item, links_data=links_data
        )
        return item

    def update(self, instance, validated_data):
        links_data = validated_data.pop('links', [])
        update_or_create_links(
            instance_type="item", model=ItemLink, instance=instance, links_data=links_data
        )
        return super().update(instance, validated_data)

    def update_or_create(self, look_up, validated_data):
        """
        Update or create the item object selected by kwargs and return the instance.
        When no item object matching the kwargs selection, a new item is created.
        Args:
            validated_data: dict
                Copy of the validated_data to use for update
            kwargs: dict
                Object selection arguments (NOTE: the selection arguments must match a unique
                object in DB otherwise an IntegrityError will be raised)
        Returns: tuple
            Item instance and True if created otherwise false
        """
        links_data = validated_data.pop('links', [])
        item, created = Item.objects.update_or_create(**look_up, defaults=validated_data)
        update_or_create_links(
            instance_type="item", model=ItemLink, instance=item, links_data=links_data
        )
        return item, created

    def validate(self, attrs):
        if (
            not self.partial or \
            'properties_datetime' in attrs or \
            'properties_start_datetime' in attrs or \
            'properties_end_datetime' in attrs
        ):
            validate_item_properties_datetimes(
                attrs.get('properties_datetime', None),
                attrs.get('properties_start_datetime', None),
                attrs.get('properties_end_datetime', None)
            )
        else:
            logger.info(
                'Skip validation of item properties datetimes; partial update without datetimes'
            )

        validate_json_payload(self)

        return attrs


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
