import logging
from collections import OrderedDict
from urllib.parse import urlparse

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from stac_api.models.general import LandingPage
from stac_api.models.general import LandingPageLink
from stac_api.utils import get_browser_url
from stac_api.utils import get_stac_version
from stac_api.utils import get_url
from stac_api.utils import is_api_version_1
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
