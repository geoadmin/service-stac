import logging
from collections import OrderedDict

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry

from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict
from rest_framework.validators import UniqueValidator
from rest_framework_gis import serializers as gis_serializers

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import LandingPage
from stac_api.models import LandingPageLink
from stac_api.models import Provider
from stac_api.models import validate_geoadmin_variant
from stac_api.models import validate_name
from stac_api.utils import isoformat

logger = logging.getLogger(__name__)

STAC_VERSION = "0.9.0"


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
                elif isinstance(value, list) and len(value) > 0:
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

    key_identifier = 'name'

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
        return STAC_VERSION

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        api_base = settings.API_BASE
        request = self.context.get("request")
        # Add auto links
        # We use OrderedDict, although it is not necessary, because the default serializer/model for
        # links already uses OrderedDict, this way we keep consistency between auto link and user
        # link
        representation['links'][:0] = [
            OrderedDict([
                ('rel', 'self'),
                ('href', request.build_absolute_uri(f'/{api_base}/')),
                ("type", "application/json"),
                ("title", "This document"),
            ]),
            OrderedDict([
                ("rel", "service-doc"),
                ("href", request.build_absolute_uri(f"/{api_base}/static/api.html")),
                ("type", "text/html"),
                ("title", "The API documentation"),
            ]),
            OrderedDict([
                ("rel", "service-desc"),
                ("href", request.build_absolute_uri(f"/{api_base}/static/openapi.yaml")),
                ("type", "application/vnd.oai.openapi+yaml;version=3.0"),
                ("title", "The OPENAPI description of the service"),
            ]),
            OrderedDict([
                ("rel", "conformance"),
                ("href", request.build_absolute_uri(f'/{api_base}/conformance')),
                ("type", "application/json"),
                ("title", "OGC API conformance classes implemented by this server"),
            ]),
            OrderedDict([
                ('rel', 'data'),
                ('href', request.build_absolute_uri(f'/{api_base}/collections')),
                ("type", "application/json"),
                ("title", "Information about the feature collections"),
            ]),
            OrderedDict([
                ("href", request.build_absolute_uri(f"/{api_base}/search")),
                ("rel", "search"),
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
    cache_start_datetime = serializers.DateTimeField()
    cache_end_datetime = serializers.DateTimeField()

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        start = instance.cache_start_datetime
        end = instance.cache_end_datetime

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


class CollectionSerializer(NonNullModelSerializer):

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

    # NOTE: when explicitely declaring fields, we need to add the validation as for the field
    # in model !
    id = serializers.CharField(
        required=True,
        max_length=255,
        source="name",
        validators=[validate_name, UniqueValidator(queryset=Collection.objects.all())]
    )
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
        return STAC_VERSION

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
        collection = Collection.objects.create(**validated_data)
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

    def to_representation(self, instance):
        name = instance.name
        api_base = settings.API_BASE
        request = self.context.get("request")
        representation = super().to_representation(instance)
        # Add auto links
        # We use OrderedDict, although it is not necessary, because the default serializer/model for
        # links already uses OrderedDict, this way we keep consistency between auto link and user
        # link
        representation['links'][:0] = [
            OrderedDict([
                ('rel', 'self'),
                ('href', request.build_absolute_uri(f'/{api_base}/collections/{name}')),
            ]),
            OrderedDict([
                ('rel', 'root'),
                ('href', request.build_absolute_uri(f'/{api_base}/')),
            ]),
            OrderedDict([
                ('rel', 'parent'),
                ('href', request.build_absolute_uri(f'/{api_base}/collections')),
            ]),
            OrderedDict([
                ('rel', 'items'),
                ('href', request.build_absolute_uri(f'/{api_base}/collections/{name}/items')),
            ])
        ]
        return representation


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
    datetime = serializers.DateTimeField(
        source='properties_datetime', allow_null=True, required=False
    )
    start_datetime = serializers.DateTimeField(
        source='properties_start_datetime', allow_null=True, required=False
    )
    end_datetime = serializers.DateTimeField(
        source='properties_end_datetime', allow_null=True, required=False
    )
    title = serializers.CharField(
        source='properties_title', required=False, allow_blank=True, max_length=255
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
    # pylint: disable=abstract-method
    key_identifier = 'name'


class AssetSerializer(NonNullModelSerializer):

    class Meta:
        model = Asset
        list_serializer_class = AssetsDictSerializer
        fields = [
            'name',
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

    # NOTE: when explicitely declaring fields, we need to add the validation as for the field
    # in model !
    type = serializers.CharField(source='media_type', max_length=200)
    # Here we need to explicitely define these fields with the source, because they are renamed
    # in the get_fields() method
    eo_gsd = serializers.FloatField(source='eo_gsd', required=False, allow_null=True)
    geoadmin_lang = serializers.ChoiceField(
        source='geoadmin_lang',
        choices=['de', 'fr', 'it', 'rm', 'en'],
        required=False,
        allow_blank=True
    )
    geoadmin_variant = serializers.CharField(
        source='geoadmin_variant',
        max_length=15,
        allow_null=True,
        validators=[validate_geoadmin_variant]
    )
    proj_epsg = serializers.IntegerField(source='proj_epsg', allow_null=True)
    checksum_multihash = serializers.CharField(source='checksum_multihash', max_length=255)
    # read only fields
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)

    def get_fields(self):
        fields = super().get_fields()
        # This is a hack to allow fields with special characters
        fields['eo:gsd'] = fields.pop('eo_gsd')
        fields['proj:epsg'] = fields.pop('proj_epsg')
        fields['geoadmin:variant'] = fields.pop('geoadmin_variant')
        fields['geoadmin:lang'] = fields.pop('geoadmin_lang')
        fields['checksum:multihash'] = fields.pop('checksum_multihash')
        return fields


class ItemSerializer(NonNullModelSerializer):

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

    # NOTE: when explicitely declaring fields, we need to add the validation as for the field
    # in model !
    collection = serializers.SlugRelatedField(slug_field='name', queryset=Collection.objects.all())
    id = serializers.CharField(
        source='name',
        required=True,
        max_length=255,
        validators=[validate_name, UniqueValidator(queryset=Collection.objects.all())]
    )
    properties = ItemsPropertiesSerializer(source='*', required=True)
    geometry = gis_serializers.GeometryField(required=True)
    links = ItemLinkSerializer(required=False, many=True)
    # read only fields
    type = serializers.ReadOnlyField(default='Feature')
    bbox = BboxSerializer(source='*', read_only=True)
    assets = AssetSerializer(many=True, read_only=True)
    stac_extensions = serializers.SerializerMethodField()
    stac_version = serializers.SerializerMethodField()

    def get_stac_extensions(self, obj):
        return list()

    def get_stac_version(self, obj):
        return STAC_VERSION

    def to_representation(self, instance):
        collection = instance.collection.name
        name = instance.name
        api = settings.API_BASE
        request = self.context.get("request")
        representation = super().to_representation(instance)
        # Add auto links
        # We use OrderedDict, although it is not necessary, because the default serializer/model for
        # links already uses OrderedDict, this way we keep consistency between auto link and user
        # link
        representation['links'][:0] = [
            OrderedDict([
                ('rel', 'self'),
                (
                    'href',
                    request.build_absolute_uri(f'/{api}/collections/{collection}/items/{name}')
                ),
            ]),
            OrderedDict([
                ('rel', 'root'),
                ('href', request.build_absolute_uri(f'/{api}/')),
            ]),
            OrderedDict([
                ('rel', 'parent'),
                ('href', request.build_absolute_uri(f'/{api}/collections/{collection}/items')),
            ]),
            OrderedDict([
                ('rel', 'collection'),
                ('href', request.build_absolute_uri(f'/{api}/collections/{collection}')),
            ])
        ]
        return representation

    def create(self, validated_data):
        links_data = validated_data.pop('links', [])
        item = Item.objects.create(**validated_data)
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
