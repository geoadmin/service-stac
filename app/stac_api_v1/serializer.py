from rest_framework import serializers

from stac_api.models import Collection
from stac_api.models import LandingPage
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import LandingPageSerializer


class V1LandingPageSerializer(LandingPageSerializer):

    class Meta:
        model = LandingPage
        fields = ['id', 'title', 'description', 'links', 'stac_version']

    stac_version = serializers.SerializerMethodField()

    def get_stac_version(self, obj=None):
        return "1.0.0"


class V1CollectionSerializer(CollectionSerializer):

    class Meta:
        model = Collection
        fields = [
            'published',
            'stac_version',
            'stac_extensions',
            'id',
            'title',
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

    def get_stac_version(self, obj):
        return 'v1.0.0'
