from rest_framework import serializers
from stac_api.models import Keyword, Provider, Link, Collection, Item, Asset


class CollectionSerializer(serializers.Serializer):

    # TODO: Do we have to take the automatically created primary_key field
    # into account here, does it have to be serialized?
    # (In 0001_initial.py, there is an auto-generated entry "serialize=False" for the
    # primary-key field.)
    crs = serializers.URLField(required=False)
    created = serializers.DateTimeField(required=True)  # datetime
    updated = serializers.DateTimeField(required=True)  # datetime
    description = serializers.CharField(required=True)  # string
    start_date = serializers.DateTimeField(allow_null=True)
    end_date = serializers.DateTimeField(allow_null=True)
    southwest = serializers.ListField(child=serializers.FloatField(), allow_empty=True)
    northeast = serializers.ListField(child=serializers.FloatField(), allow_empty=True)
    collection_name = serializers.CharField(max_length=255)  # string
    item_type = serializers.CharField(default="Feature", max_length=20)  # string
    keywords = serializers.StringRelatedField(many=True)
    license = serializers.CharField(max_length=30)  # string
    links = serializers.StringRelatedField(many=True)
    providers = serializers.StringRelatedField(many=True)
    stac_extension = serializers.ListField(child=serializers.CharField(max_length=255),)
    stac_version = serializers.CharField(max_length=10)  # string

    summaries_eo_gsd = serializers.ListField(
        child=serializers.FloatField(), allow_empty=True, allow_null=True
    )
    summaries_proj = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True, allow_null=True
    )
    geoadmin_variant = serializers.ListField(
        child=serializers.CharField(max_length=15), allow_empty=True, allow_null=True
    )
    title = serializers.CharField(allow_blank=True, max_length=255)  # string

    class Meta:
        model = Keyword
        fields = ['keywords']

        model = Link
        fields = ['links']

        model = Provider
        fields = ['providers']

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

        super().to_internal_value(data)

    def create(self, validated_data):
        """
        Create and return a new `stac_api` instance, given the validated data.
        """
        return Collection.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """
        Update and return an existing `stac_api` instance, given the validated data.
        """

        instance.crs = validated_data.get('crs', instance.crs)
        instance.created = validated_data.get('created', instance.created)
        instance.updated = validated_data.get('updated', instance.updated)
        instance.description = validated_data.get('description', instance.description)
        instance.start_date = validated_data.get('start_date', instance.start_date)
        instance.end_date = validated_data.get('end_date', instance.end_date)
        instance.southwest = validated_data.get('southwest', instance.southwest)
        instance.northeast = validated_data.get('northeast', instance.northeast)
        instance.collection_name = validated_data.get('collection_name', instance.collection_name)
        instance.item_type = validated_data.get('item_type', instance.item_type)
        instance.keywords = validated_data.get('keywords', instance.keywords)
        instance.license = validated_data.get('license', instance.license)
        instance.links = validated_data.get('links', instance.links)
        instance.providers = validated_data.get('providers', instance.providers)
        instance.stac_extension = validated_data.get('stac_extension', instance.stac_extension)
        instance.stac_version = validated_data.get('stac_version', instance.stac_version)
        instance.summaries_eo_gsd = validated_data.get(
            'summaries_eo_gsd', instance.summaries_eo_gsd
        )
        instance.summaries_proj = validated_data.get('summaries_proj', instance.summaries_proj)
        instance.geoadmin_variant = validated_data.get(
            'geoadmin_variant', instance.geoadmin_variant
        )
        instance.title = validated_data.get('title', instance.title)

        instance.save()
        return instance
