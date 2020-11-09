import logging
from collections import OrderedDict

from django.contrib.gis.geos import GEOSGeometry

from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict
from rest_framework_gis import serializers as gis_serializers

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import Keyword
from stac_api.models import Provider
from stac_api.models import get_default_stac_extensions

logger = logging.getLogger(__name__)


class NonNullModelSerializer(serializers.ModelSerializer):
    """Filter fields with null value

    Best practice is to not include (optional) fields whose
    value is None.
    """

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret = OrderedDict(filter(lambda x: x[1] is not None, ret.items()))
        return ret


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


class KeywordSerializer(NonNullModelSerializer):

    name = serializers.CharField(max_length=64)

    class Meta:
        model = Keyword
        fields = ['name']

    def create(self, validated_data):
        """
        Create and return a new `Keyword` instance, given the validated data.
        """
        logger.debug('Create Keyword', extra={'validated_data': validated_data})
        return Collection.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """
        Update and return an existing `Keyword` instance, given the validated data.
        """
        instance.name = validated_data.get('name', instance.name)

        logger.debug('Update Keyword %s', instance.name, extra={'validated_data': validated_data})

        instance.save()
        return instance


class ProviderSerializer(NonNullModelSerializer):

    name = serializers.CharField(allow_blank=False, max_length=200)  # string
    description = serializers.CharField()  # string
    roles = serializers.ListField(child=serializers.CharField(max_length=9))  # [string]
    url = serializers.URLField()  # string

    class Meta:
        model = Provider
        fields = ['name', 'roles', 'url', 'description']
        # most likely not all fields necessary here, can be adapted

    def create(self, validated_data):
        """
        Create and return a new `Provider` instance, given the validated data.
        """
        logger.debug('Create Provider', extra={'validated_data': validated_data})
        return Collection.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """
        Update and return an existing `Provider` instance, given the validated data.
        """

        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.roles = validated_data.get('roles', instance.roles)
        instance.url = validated_data.get('url', instance.url)

        logger.debug('Update Provider %s', instance.name, extra={'validated_data': validated_data})

        instance.save()
        return instance


class ExtentTemporalSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    cache_start_datetime = serializers.DateTimeField(format='%Y-%m-%dT%H:%M:%SZ')
    cache_end_datetime = serializers.DateTimeField(format='%Y-%m-%dT%H:%M:%SZ')

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        start = instance.cache_start_datetime
        end = instance.cache_end_datetime

        if start is not None:
            start = start.strftime('%Y-%m-%dT%H:%M:%SZ')

        if end is not None:
            end = end.strftime('%Y-%m-%dT%H:%M:%SZ')

        ret["temporal_extent"] = {"interval": [[start, end]]}

        return ret["temporal_extent"]


class ExtentSpatialSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    extent_geometry = gis_serializers.GeometryField

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
        fields = ['href', 'rel', 'link_type', 'title']


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
            'keywords',
            'crs',
            'itemType'
        ]
        # crs and keywords not in sample data, but in specs..

    crs = serializers.SerializerMethodField()
    created = serializers.DateTimeField(required=True, format='%Y-%m-%dT%H:%M:%SZ')  # datetime
    updated = serializers.DateTimeField(required=True, format='%Y-%m-%dT%H:%M:%SZ')  # datetime
    description = serializers.CharField(required=True)  # string
    extent = ExtentSerializer(read_only=True, source="*")
    summaries = serializers.JSONField(read_only=True)
    id = serializers.CharField(max_length=255, source="collection_name")  # string
    keywords = KeywordSerializer(many=True, read_only=True)
    license = serializers.CharField(max_length=30)  # string
    links = CollectionLinkSerializer(many=True, read_only=True)
    providers = ProviderSerializer(many=True)
    stac_extensions = serializers.SerializerMethodField()
    stac_version = serializers.SerializerMethodField()
    title = serializers.CharField(allow_blank=True, max_length=255)  # string
    itemType = serializers.ReadOnlyField(default="Feature")  # pylint: disable=invalid-name

    def get_crs(self, obj):
        return ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"]

    def get_stac_extensions(self, obj):
        return get_default_stac_extensions()

    def get_stac_version(self, obj):
        return "0.9.0"

    def create(self, validated_data):
        """
        Create and return a new `Collection` instance, given the validated data.
        """
        return Collection.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """
        Update and return an existing `Collection` instance, given the validated data.
        """

        instance.save()
        return instance


class ItemLinkSerializer(NonNullModelSerializer):

    class Meta:
        model = ItemLink
        fields = ['href', 'rel', 'link_type', 'title']


class ItemsPropertiesSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    # ItemsPropertiesSerializer is a nested serializer and don't directly create/write instances
    # therefore we don't need to implement the super method create() and update()
    datetime = serializers.DateTimeField(source='properties_datetime', allow_null=True)
    start_datetime = serializers.DateTimeField(source='properties_start_datetime', allow_null=True)
    end_datetime = serializers.DateTimeField(source='properties_end_datetime', allow_null=True)
    eo_gsd = serializers.ListField(required=True, source='properties_eo_gsd')
    title = serializers.CharField(required=True, source='properties_title', max_length=255)

    def get_fields(self):
        fields = super().get_fields()
        # This is a hack to allow fields with special characters
        fields['eo:gsd'] = fields.pop('eo_gsd')
        logger.debug('Updated fields name: %s', fields)
        return fields


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
    key_identifier = 'asset_name'


class AssetSerializer(NonNullModelSerializer):
    type = serializers.CharField(source='media_type', max_length=200)
    eo_gsd = serializers.FloatField(source='eo_gsd')
    geoadmin_lang = serializers.CharField(source='geoadmin_lang', max_length=2)
    geoadmin_variant = serializers.CharField(source='geoadmin_variant', max_length=15)
    proj_epsg = serializers.IntegerField(source='proj_epsg')
    checksum_multihash = serializers.CharField(source='checksum_multihash', max_length=255)

    class Meta:
        model = Asset
        list_serializer_class = AssetsDictSerializer
        fields = [
            'asset_name',
            'title',
            'type',
            'href',
            'description',
            'eo_gsd',
            'geoadmin_lang',
            'geoadmin_variant',
            'proj_epsg',
            'checksum_multihash',
        ]

    def get_fields(self):
        fields = super().get_fields()
        # This is a hack to allow fields with special characters
        fields['eo:gsd'] = fields.pop('eo_gsd')
        fields['proj:epsg'] = fields.pop('proj_epsg')
        fields['geoadmin:variant'] = fields.pop('geoadmin_variant')
        fields['geoadmin:lang'] = fields.pop('geoadmin_lang')
        fields['checksum:multihash'] = fields.pop('checksum_multihash')
        logger.debug('Updated fields name: %s', fields)
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
            'assets',
        ]

    collection = serializers.StringRelatedField()
    id = serializers.CharField(source='item_name', required=True, max_length=255)
    properties = ItemsPropertiesSerializer(source='*')
    geometry = gis_serializers.GeometryField()
    # read only fields
    links = ItemLinkSerializer(many=True, read_only=True)
    type = serializers.ReadOnlyField(default='Feature')
    bbox = BboxSerializer(source='*', read_only=True)
    assets = AssetSerializer(many=True, read_only=True)
    stac_extensions = serializers.SerializerMethodField()
    stac_version = serializers.SerializerMethodField()

    def get_stac_extensions(self, obj):
        return get_default_stac_extensions()

    def get_stac_version(self, obj):
        return "0.9.0"
