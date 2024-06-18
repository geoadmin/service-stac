import logging
import re
from urllib.parse import urlparse

from django.conf import settings
from django.utils.cache import add_never_cache_headers
from django.utils.cache import get_max_age
from django.utils.cache import patch_cache_control
from django.utils.cache import patch_response_headers

logger = logging.getLogger(__name__)

STAC_BASE = settings.STAC_BASE


class CacheHeadersMiddleware:
    '''Middleware that adds appropriate cache headers to GET and HEAD methods.

    NOTE: /checker, /get-token, /metrics and /{healthcheck} endpoints are marked as never cache.
    '''

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        response = self.get_response(request)

        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            return response

        # Code to be executed for each request/response after
        # the view is called.

        # match /xxx or /api/stac/xxx or status code 502, 503, 504, 507
        # f.ex. /metrics, /checker, /api/stac/{healthcheck}, /api/stac/get-token
        if re.match(fr'^(/{STAC_BASE})?/\w+$',
                    request.path) or response.status_code in (502, 503, 504, 507):
            add_never_cache_headers(response)
        elif response.status_code >= 500:
            patch_cache_control(response, public=True)
            patch_response_headers(response, cache_timeout=10)
        elif (
            request.method in ('GET', 'HEAD') and
            not request.path.startswith(urlparse(settings.STATIC_URL).path) and
            get_max_age(response) is None  # only set if not already set by the application
        ):
            logger.debug(
                "Patching default cache headers for request %s %s",
                request.method,
                request.path,
                extra={"request": request}
            )
            patch_response_headers(response, settings.CACHE_MIDDLEWARE_SECONDS)
            patch_cache_control(response, public=True)

        return response
