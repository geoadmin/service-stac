import logging

from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from django.conf import settings
from django.http import HttpResponseRedirect

logger = logging.getLogger(__name__)

STAC_BASE = settings.STAC_BASE
STAC_BASE_V = settings.STAC_BASE_V

class OIDCLoginMiddleware:
    '''Middleware that enforce OIDC login on all endpoints.'''

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path.startswith('/oidc/'):
            # Redirect to OIDC login page if user is not authenticated
            return HttpResponseRedirect('/oidc/authenticate/?next=' + request.path)

        return self.get_response(request)
