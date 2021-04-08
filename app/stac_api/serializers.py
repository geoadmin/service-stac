import logging
from collections import OrderedDict
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.urls import reverse

from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict
from rest_framework.validators import UniqueValidator
from rest_framework_gis import serializers as gis_serializers

from stac_api.models import Asset
from stac_api.models import AssetUpload
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import ConformancePage
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import LandingPage
from stac_api.models import LandingPageLink
from stac_api.models import Provider
from stac_api.utils import build_asset_href
from stac_api.utils import isoformat
from stac_api.validators import MEDIA_TYPES_MIMES
from stac_api.validators import validate_asset_name
from stac_api.validators import validate_asset_name_with_media_type
from stac_api.validators import validate_checksum_multihash_sha256
from stac_api.validators import validate_geoadmin_variant
from stac_api.validators import validate_item_properties_datetimes
from stac_api.validators import validate_name
from stac_api.validators_serializer import validate_json_payload
from stac_api.validators_serializer import validate_uniqueness_and_create

logger = logging.getLogger(__name__)


def create_or_update_str(created):
    if created:
        return 'create'
    return 'update'


def update_or_create_links(model, instance, instance_type, links_data):
    '''Update or create links for a model

    Update the given links list within a model instance or create them when they don't exists yet.
    Args:
        model: model class on which to update/create links (Collection or Item)
        instance: model instance on which to update/create links
        instance_type: (str) instance type name string to use for filtering ('collection' or 'item')
        links_data: list of links dictionary to add/update
    '''
    links_ids = []
    for link_data in links_data:
        link, created = model.objects.get_or_create(
            **{instance_type: instance},
            rel=link_data["rel"],
            defaults={
                'href': link_data.get('href', None),
                'link_type': link_data.get('link_type', None),
                'title': link_data.get('title', None)
            }
        )
        logger.debug(
            '%s link %s',
            create_or_update_str(created),
            link.href,
            extra={
                instance_type: instance.name, "link": link_data
            }
        )
        links_ids.append(link.id)
        # the duplicate here is necessary to update the values in
        # case the object already exists
        link.link_type = link_data.get('link_type', link.link_type)
        link.title = link_data.get('title', link.title)
        link.href = link_data.get('href', link.rel)
        link.full_clean()
        link.save()

    # Delete link that were not mentioned in the payload anymore
    deleted = model.objects.filter(**{instance_type: instance},).exclude(id__in=links_ids).delete()
    logger.info(
        "deleted %d stale links for %s %s",
        deleted[0],
        instance_type,
        instance.name,
        extra={instance_type: instance}
    )


def get_relation_links(request, view, view_args):
    '''Returns a list of auto generated relation links

    Returns the self, root and parent auto generated links.

    Args:
        request: HttpRequest
            request object
        view: string
            name of the view that originate the call
        view_args: list
            args to construct the view path

    Returns: list
        List of auto generated links
    '''
    self_url = request.build_absolute_uri(reverse(view, args=view_args))
    return [
        OrderedDict([
            ('rel', 'self'),
            ('href', self_url),
        ]),
        OrderedDict([
            ('rel', 'root'),
            ('href', request.build_absolute_uri(reverse('landing-page'))),
        ]),
        OrderedDict([
            ('rel', 'parent'),
            ('href', self_url.rsplit('/', maxsplit=1)[0]),
        ]),
    ]


def get_url(request, view, args=None):
    '''Get an full url based on a view name'''
    return request.build_absolute_uri(reverse(view, args=args))


class UpsertModelSerializerMixin:
    """Add support for Upsert in serializer
    """

    def upsert(self, look_up, **kwargs):
        """
        Update or insert an instance and return it.

        Args:
            look_up: dict
                Must be a unique query to be used in the objects.update_or_create(**look_up) method.
            **kwargs:
                Extra key=value pairs to pass as validated_data to update_or_create(). For example
                relationships that are not serialized but part of the request path can be given
                as kwargs.
        """
        validated_data = {**self.validated_data, **kwargs}
        self.instance, created = self.update_or_create(look_up, validated_data)
        return self.instance, created

    def update_or_create(self, look_up, validated_data):
        """This method must be implemented by the serializer and must make use of the DB
        objects.update_or_create() method.

        Args:
           look_up: dict
                Must be a unique query to be used in the objects.update_or_create(**look_up)
                method.
            validated_data: dict
                Copy of the validated_data to be used as defaults in the
                objects.update_or_create(defaults=validated_data) method.
        """
        raise NotImplementedError("update_or_create() not implemented")


class NonNullModelSerializer(serializers.ModelSerializer):
    """Filter fields with null value

    Best practice is to not include (optional) fields whose
    value is None.
    """

    def to_representation(self, instance):

        def filter_null(obj):
            filtered_obj = {}
            if isinstance(obj, OrderedDict):
                filtered_obj = OrderedDict()
            for key, value in obj.items():
                if isinstance(value, dict):
                    filtered_obj[key] = filter_null(value)
                # then links array might be empty at this point,
                # but that in the view the auto generated links are added anyway
                elif isinstance(value, list) and key != 'links':
                    if len(value) > 0:
                        filtered_obj[key] = value
                elif value is not None:
                    filtered_obj[key] = value
            return filtered_obj

        obj = super().to_representation(instance)
        return filter_null(obj)


class DictSerializer(serializers.ListSerializer):
    '''Represent objects within a dictionary instead of a list

    By default the Serializer with `many=True` attribute represent all objects within a list.
    Here we overwrite the ListSerializer to instead represent multiple objects using a dictionary
    where the object identifier is used as key.

    For example the following list:

        [{
                'name': 'object1',
                'description': 'This is object 1'
            }, {
                'name': 'object2',
                'description': 'This is object 2'
        }]

    Would be represented as follow:

        {
            'object1': {'description': 'This is object 1'},
            'object2': {'description': 'This is object 2'}
        }
    '''

    # pylint: disable=abstract-method

    key_identifier = 'id'

    def to_representation(self, data):
        objects = super().to_representation(data)
        return {obj.pop(self.key_identifier): obj for obj in objects}

    @property
    def data(self):
        ret = super(serializers.ListSerializer, self).data
        return ReturnDict(ret, serializer=self)


class LandingPageLinkSerializer(serializers.ModelSerializer):

    class Meta:
        model = LandingPageLink
        fields = ['href', 'rel', 'link_type', 'title']


class ConformancePageSerializer(serializers.ModelSerializer):

    class Meta:
        model = ConformancePage
        fields = ['conformsTo']


class LandingPageSerializer(serializers.ModelSerializer):

    class Meta:
        model = LandingPage
        fields = ['id', 'title', 'description', 'links', 'stac_version']

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
        return settings.STAC_VERSION

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get("request")

        spec_base = urlparse(settings.STATIC_SPEC_URL).path.strip('/')
        # Add auto links
        # We use OrderedDict, although it is not necessary, because the default serializer/model for
        # links already uses OrderedDict, this way we keep consistency between auto link and user
        # link
        representation['links'][:0] = [
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
        ]
        return representation


class ProviderSerializer(NonNullModelSerializer):

    class Meta:
        model = Provider
        fields = ['name', 'roles', 'url', 'description']


class ExtentTemporalSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    extent_start_datetime = serializers.DateTimeField()
    extent_end_datetime = serializers.DateTimeField()

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        start = instance.extent_start_datetime
        end = instance.extent_end_datetime

        if start is not None:
            start = isoformat(start)

        if end is not None:
            end = isoformat(end)

        ret["temporal_extent"] = {"interval": [[start, end]]}

        return ret["temporal_extent"]


class ExtentSpatialSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    extent_geometry = gis_serializers.GeometryField()

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # handle empty field
        if instance.extent_geometry is None:
            ret["bbox"] = {"bbox": [[]]}
        else:
            bbox = GEOSGeometry(instance.extent_geometry).extent
            bbox = list(bbox)
            ret["bbox"] = {"bbox": [bbox]}
        return ret["bbox"]


class ExtentSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    spatial = ExtentSpatialSerializer(source="*")
    temporal = ExtentTemporalSerializer(source="*")


class CollectionLinkSerializer(NonNullModelSerializer):

    class Meta:
        model = CollectionLink
        fields = ['href', 'rel', 'title', 'type']

    # NOTE: when explicitely declaring fields, we need to add the validation as for the field
    # in model !
    type = serializers.CharField(
        required=False, allow_blank=True, max_length=150, source="link_type"
    )


class CollectionSerializer(NonNullModelSerializer, UpsertModelSerializerMixin):

    class Meta:
        model = Collection
        fields = [
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
            'itemType'
        ]
        # crs not in sample data, but in specs..
        validators = []  # Remove a default "unique together" constraint.
        # (see:
        # https://www.django-rest-framework.org/api-guide/validators/#limitations-of-validators)

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
    extent = ExtentSerializer(read_only=True, source="*")
    summaries = serializers.JSONField(read_only=True)
    stac_extensions = serializers.SerializerMethodField(read_only=True)
    stac_version = serializers.SerializerMethodField(read_only=True)
    itemType = serializers.ReadOnlyField(default="Feature")  # pylint: disable=invalid-name

    def get_crs(self, obj):
        return ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"]

    def get_stac_extensions(self, obj):
        return list()

    def get_stac_version(self, obj):
        return settings.STAC_VERSION

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
                create_or_update_str(created),
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
        # Add auto links
        # We use OrderedDict, although it is not necessary, because the default serializer/model for
        # links already uses OrderedDict, this way we keep consistency between auto link and user
        # link
        representation['links'][:0] = get_relation_links(request, 'collection-detail', [name]) + [
            OrderedDict([
                ('rel', 'items'),
                ('href', get_url(request, 'items-list', [name])),
            ])
        ]
        return representation

    def validate(self, attrs):
        validate_json_payload(self)
        return attrs


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
        source='properties_title', required=False, allow_blank=False, max_length=255, default=None
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

        return build_asset_href(request, path)


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
            'geoadmin_lang',
            'geoadmin_variant',
            'proj_epsg',
            'checksum_multihash',
            'created',
            'updated'
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
    type = serializers.ChoiceField(
        source='media_type',
        required=True,
        choices=MEDIA_TYPES_MIMES,
        allow_null=False,
        allow_blank=False
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
    href = HrefField(source='file', read_only=True)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)

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

    def validate(self, attrs):
        if not self.partial:
            validate_asset_name_with_media_type(attrs.get('name'), attrs.get('media_type'))
        if self.partial and ('name' in attrs or 'media_type' in attrs):
            validate_asset_name_with_media_type(
                attrs.get('name', self.instance.name),
                attrs.get('media_type', self.instance.media_type)
            )

        validate_json_payload(self)

        return attrs

    def get_fields(self):
        fields = super().get_fields()
        # This is a hack to allow fields with special characters
        fields['eo:gsd'] = fields.pop('eo_gsd')
        fields['proj:epsg'] = fields.pop('proj_epsg')
        fields['geoadmin:variant'] = fields.pop('geoadmin_variant')
        fields['geoadmin:lang'] = fields.pop('geoadmin_lang')
        fields['checksum:multihash'] = fields.pop('checksum_multihash')
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
        representation['links'] = \
            get_relation_links(request, 'asset-detail', [collection, item, name]) \
            + [
                OrderedDict([
                    ('rel', 'item'),
                    ('href', get_url(request, 'item-detail', [collection, item])),
                ]),
                OrderedDict([
                    ('rel', 'collection'),
                    ('href', get_url(request, 'collection-detail', [collection])),
                ])
            ]
        return representation


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
            'eo_gsd',
            'geoadmin_lang',
            'geoadmin_variant',
            'proj_epsg',
            'checksum_multihash',
            'created',
            'updated'
        ]


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
        return list()

    def get_stac_version(self, obj):
        return settings.STAC_VERSION

    def to_representation(self, instance):
        collection = instance.collection.name
        name = instance.name
        request = self.context.get("request")
        representation = super().to_representation(instance)
        # Add auto links
        # We use OrderedDict, although it is not necessary, because the default serializer/model for
        # links already uses OrderedDict, this way we keep consistency between auto link and user
        # link
        representation['links'][:0] = \
            get_relation_links(request, 'item-detail', [collection, name]) \
            + [
                OrderedDict([
                    ('rel', 'collection'),
                    ('href', get_url(request, 'collection-detail', [collection])),
                ])
            ]
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
    # pylint: disable=abstract-method
    etag = serializers.CharField(source='ETag', allow_blank=False, required=True)
    part_number = serializers.IntegerField(
        source='PartNumber', min_value=1, max_value=10000, required=True, allow_null=False
    )


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
            'urls',
            'ended',
            'parts'
        ]

    checksum_multihash = serializers.CharField(
        source='checksum_multihash',
        max_length=255,
        required=True,
        allow_blank=False,
        validators=[validate_checksum_multihash_sha256]
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
        fields['checksum:multihash'] = fields.pop('checksum_multihash')
        return fields
