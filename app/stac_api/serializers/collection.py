import logging

from django.contrib.gis.geos import GEOSGeometry

from rest_framework import serializers

from stac_api.models import Collection
from stac_api.models import CollectionAsset
from stac_api.models import CollectionLink
from stac_api.models import Provider
from stac_api.serializers.utils import AssetsDictSerializer
from stac_api.serializers.utils import HrefField
from stac_api.serializers.utils import NonNullModelSerializer
from stac_api.serializers.utils import UpsertModelSerializerMixin
from stac_api.serializers.utils import get_relation_links
from stac_api.serializers.utils import update_or_create_links
from stac_api.utils import get_stac_version
from stac_api.utils import is_api_version_1
from stac_api.utils import isoformat
from stac_api.validators import normalize_and_validate_media_type
from stac_api.validators import validate_asset_name
from stac_api.validators import validate_asset_name_with_media_type
from stac_api.validators import validate_name
from stac_api.validators_serializer import validate_json_payload
from stac_api.validators_serializer import validate_uniqueness_and_create

logger = logging.getLogger(__name__)


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


class CollectionAssetBaseSerializer(NonNullModelSerializer, UpsertModelSerializerMixin):
    '''Collection asset serializer base class
    '''

    class Meta:
        model = CollectionAsset
        fields = [
            'id',
            'title',
            'type',
            'href',
            'description',
            'roles',
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
    proj_epsg = serializers.IntegerField(source='proj_epsg', allow_null=True, required=False)
    # read only fields
    checksum_multihash = serializers.CharField(source='checksum_multihash', read_only=True)
    href = HrefField(source='file', read_only=True)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)

    # helper variable to provide the collection for upsert validation
    # see views.AssetDetail.perform_upsert
    collection = None

    def create(self, validated_data):
        asset = validate_uniqueness_and_create(CollectionAsset, validated_data)
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
        asset, created = CollectionAsset.objects.update_or_create(
            **look_up,
            defaults=validated_data,
            )
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
        fields['proj:epsg'] = fields.pop('proj_epsg')
        fields['file:checksum'] = fields.pop('checksum_multihash')

        # Older versions of the api still use different name
        request = self.context.get('request')
        if not is_api_version_1(request):
            fields['checksum:multihash'] = fields.pop('file:checksum')
            fields.pop('roles', None)

        return fields


class CollectionAssetSerializer(CollectionAssetBaseSerializer):
    '''Collection Asset serializer for the collection asset views

    This serializer adds the links list attribute.
    '''

    def to_representation(self, instance):
        collection = instance.collection.name
        name = instance.name
        request = self.context.get("request")
        representation = super().to_representation(instance)
        # Add auto links
        # We use OrderedDict, although it is not necessary, because the default serializer/model for
        # links already uses OrderedDict, this way we keep consistency between auto link and user
        # link
        representation['links'] = get_relation_links(
            request, 'collection-asset-detail', [collection, name]
        )
        return representation


class CollectionAssetsForCollectionSerializer(CollectionAssetBaseSerializer):
    '''Collection assets serializer for nesting them inside the collection

    Assets should be nested inside their collection but using a dictionary instead of a list and
    without links.
    '''

    class Meta:
        model = CollectionAsset
        list_serializer_class = AssetsDictSerializer
        fields = [
            'id',
            'title',
            'type',
            'href',
            'description',
            'roles',
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
    assets = CollectionAssetsForCollectionSerializer(many=True, read_only=True)

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
