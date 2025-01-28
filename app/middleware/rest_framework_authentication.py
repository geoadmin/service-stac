from django.conf import settings

from rest_framework.authentication import BasicAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.authentication import TokenAuthentication


class RestrictedBasicAuthentication(BasicAuthentication):
    """ A Django rest framework basic authentication class that skips v1 of STAC API. """

    def authenticate(self, request):
        if settings.FEATURE_AUTH_RESTRICT_V1 and request.path.startswith(
            f'/{settings.STAC_BASE}/v1/'
        ):
            return None

        return super().authenticate(request)


class RestrictedSessionAuthentication(SessionAuthentication):
    """ A Django rest framework session authentication class that skips v1 of STAC API. """

    def authenticate(self, request):
        if settings.FEATURE_AUTH_RESTRICT_V1 and request.path.startswith(
            f'/{settings.STAC_BASE}/v1/'
        ):
            return None

        return super().authenticate(request)


class RestrictedTokenAuthentication(TokenAuthentication):
    """ A Django rest framework token authentication class that skips v1 of STAC API. """

    def authenticate(self, request):
        if settings.FEATURE_AUTH_RESTRICT_V1 and request.path.startswith(
            f'/{settings.STAC_BASE}/v1/'
        ):
            return None

        return super().authenticate(request)
