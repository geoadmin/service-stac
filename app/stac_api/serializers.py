from rest_framework import serializers

# from stac_api.models import Item
# from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import Keyword
from stac_api.models import Link
from stac_api.models import Provider

# pylint: disable=fixme


class KeywordSerializer(serializers.ModelSerializer):

    name = serializers.CharField(max_length=64)

    class Meta:
        model = Keyword
        fields = ['name']

    def create(self, validated_data):
        """
        Create and return a new `Keyword` instance, given the validated data.
        """
        return Collection.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """
        Update and return an existing `Keyword` instance, given the validated data.
        """

        instance.name = validated_data.get('name', instance.name)

        instance.save()
        return instance


class LinkSerializer(serializers.ModelSerializer):

    href = serializers.URLField()  # string
    rel = serializers.CharField(max_length=30)  # string
    link_type = serializers.CharField(allow_blank=True, max_length=150)  # string
    title = serializers.CharField(allow_blank=True, max_length=255)  # string

    class Meta:
        model = Link
        fields = ['href', 'rel', 'link_type', 'title']
        # most likely not all fields necessary here, can be adapted

    def create(self, validated_data):
        """
        Create and return a new `Link` instance, given the validated data.
        """
        return Collection.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """
        Update and return an existing `Link` instance, given the validated data.
        """

        instance.href = validated_data.get('href', instance.href)
        instance.rel = validated_data.get('rel', instance.rel)
        instance.link_type = validated_data.get('link_type', instance.link_type)
        instance.title = validated_data.get('title', instance.title)

        instance.save()
        return instance


class ProviderSerializer(serializers.ModelSerializer):

    name = serializers.CharField(allow_blank=False, max_length=200)  # string
    description = serializers.CharField(required=False, allow_blank=True)  # string
    roles = serializers.ListField(child=serializers.CharField(max_length=9))  # [string]
    url = serializers.URLField()  # string

    class Meta:
        model = Provider
        fields = ['name','roles','url', 'description']
        # most likely not all fields necessary here, can be adapted

    def create(self, validated_data):
        """
        Create and return a new `Provider` instance, given the validated data.
        """
        return Collection.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """
        Update and return an existing `Provider` instance, given the validated data.
        """

        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.roles = validated_data.get('roles', instance.roles)
        instance.url = validated_data.get('url', instance.url)

        instance.save()
        return instance


class CollectionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Collection
        fields = [
            'stac_version',
            'stac_extension',
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
            'crs'
        ]
    crs = serializers.ListField(child=serializers.URLField(required=False))
    created = serializers.DateTimeField(required=True)  # datetime
    updated = serializers.DateTimeField(required=True)  # datetime
    description = serializers.CharField(required=True)  # string
    extent = serializers.JSONField()
    summaries= serializers.JSONField()
    id = serializers.CharField(max_length=255, source="collection_name")  # string
    keywords = KeywordSerializer(many=True, read_only=True)
    license = serializers.CharField(max_length=30)  # string
    links = LinkSerializer(many=True)
    providers = ProviderSerializer(many=True)
    stac_extension = serializers.ListField(child=serializers.CharField(max_length=255),)
    stac_version = serializers.CharField(max_length=10)  # string
    title = serializers.CharField(allow_blank=True, max_length=255)  # string

    def to_internal_value(self, data):
        '''
        Not sure if this is the most elegant way: This function converts empty
        DateTimeFields for start_ and end_date, which are allowed to be empty
        per definition in models.py, to None, in order to catch errors.
        Unfortunately serializers don't allow 'allow_blank=True' for DateTimeFields.
        '''

        if data.get('start_date') == '':
            data['start_date'] = None

        if data.get('end_date') == '':
            data['end_date'] = None

        return super().to_internal_value(data)

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
