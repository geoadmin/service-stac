import logging

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

logger = logging.getLogger(__name__)


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


class KeywordSerializer(serializers.ModelSerializer):

    name = serializers.CharField(max_length=64)

    class Meta:
        model = Keyword
        fields = '__all__'

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


class ProviderSerializer(serializers.ModelSerializer):

    name = serializers.CharField(allow_blank=False, max_length=200)  # string
    description = serializers.CharField()  # string
    roles = serializers.ListField(child=serializers.CharField(max_length=9))  # [string]
    url = serializers.URLField()  # string

    class Meta:
        model = Provider
        fields = '__all__'
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


class CollectionLinkSerializer(serializers.ModelSerializer):

    class Meta:
        model = CollectionLink
        fields = ['href', 'rel', 'link_type', 'title']


class CollectionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Collection
        fields = '__all__'

    crs = serializers.ListField(child=serializers.URLField(required=False))
    created = serializers.DateTimeField(required=True)  # datetime
    updated = serializers.DateTimeField(required=True)  # datetime
    description = serializers.CharField(required=True)  # string
    extent = serializers.JSONField(read_only=True)
    summaries = serializers.JSONField(read_only=True)
    collection_name = serializers.CharField(max_length=255)  # string
    keywords = KeywordSerializer(many=True, read_only=True)
    license = serializers.CharField(max_length=30)  # string
    links = CollectionLinkSerializer(many=True, read_only=True)
    providers = ProviderSerializer(many=True)
    stac_extension = serializers.ListField(child=serializers.CharField(max_length=255),)
    stac_version = serializers.CharField(max_length=10)  # string
    title = serializers.CharField(allow_blank=True, max_length=255)  # string

    def create(self, validated_data):
        """
        Create and return a new `Collection` instance, given the validated data.
        """
        return Collection.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """
        Update and return an existing `Collection` instance, given the validated data.
        """

        instance.crs = validated_data.get('crs', instance.crs)
        instance.created = validated_data.get('created', instance.created)
        instance.updated = validated_data.get('updated', instance.updated)
        instance.description = validated_data.get('description', instance.description)
        instance.extent = validated_data.get('extent', instance.extent)
        instance.collection_name = validated_data.get('collection_name', instance.collection_name)
        instance.item_type = validated_data.get('item_type', instance.item_type)
        instance.keywords = validated_data.get('keywords', instance.keywords)
        instance.license = validated_data.get('license', instance.license)
        instance.links = validated_data.get('links', instance.links)
        instance.providers = validated_data.get('providers', instance.providers)
        instance.stac_extension = validated_data.get('stac_extension', instance.stac_extension)
        instance.stac_version = validated_data.get('stac_version', instance.stac_version)
        instance.title = validated_data.get('title', instance.title)

        instance.save()
        return instance


class ItemLinkSerializer(serializers.ModelSerializer):

    class Meta:
        model = ItemLink
        fields = ['href', 'rel', 'link_type', 'title']


class ItemsPropertiesSerializer(serializers.Serializer):
    # pylint: disable=abstract-method
    # ItemsPropertiesSerializer is a nested serializer and don't directly create/write instances
    # therefore we don't need to implement the super method create() and update()
    datetime = serializers.DateTimeField(required=True, source='properties_datetime')
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


class AssetSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source='media_type', max_length=200)
    eo_gsd = serializers.FloatField(source='eo_gsd')
    geoadmin_lang = serializers.CharField(source='geoadmin_lang', max_length=2)
    geoadmin_variant = serializers.CharField(source='geoadmin_variant', max_length=15)
    proj_epsq = serializers.IntegerField(source='proj_epsq')
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
            'proj_epsq',
            'checksum_multihash',
        ]

    def get_fields(self):
        fields = super().get_fields()
        # This is a hack to allow fields with special characters
        fields['eo:gsd'] = fields.pop('eo_gsd')
        fields['proj:epsq'] = fields.pop('proj_epsq')
        fields['geoadmin:variant'] = fields.pop('geoadmin_variant')
        fields['geoadmin:lang'] = fields.pop('geoadmin_lang')
        fields['checksum:multihash'] = fields.pop('checksum_multihash')
        logger.debug('Updated fields name: %s', fields)
        return fields


class ItemSerializer(serializers.ModelSerializer):

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
