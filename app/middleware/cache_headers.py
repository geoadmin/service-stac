import logging
import re
from urllib.parse import urlparse

from django.conf import settings
from django.utils.cache import add_never_cache_headers
from django.utils.cache import patch_cache_control
from django.utils.cache import patch_response_headers

logger = logging.getLogger(__name__)

STAC_BASE = settings.STAC_BASE
STAC_BASE_V = settings.STAC_BASE_V


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

        public_directives = {"public": True}

        error_directives = {
            "public": True, "must-revalidate": True, "no-cache": True, "no-store": True
        }

        # Code to be executed for each request/response after
        # the view is called.
        # match /xxx or /api/stac/xxx
        # f.ex. /metrics, /checker, /api/stac/{healthcheck}, /api/stac/get-token
        if re.match(fr'^(/{STAC_BASE})?/\w+$', request.path):
            add_never_cache_headers(response)
        elif (
            request.method in ('GET', 'HEAD') and
            not request.path.startswith(urlparse(settings.STATIC_URL).path)
        ):
            logger.debug(
                "Patching cache headers for request %s %s",
                request.method,
                request.path,
                extra={"request": request}
            )
            patch_response_headers(response, settings.CACHE_MIDDLEWARE_SECONDS)
            directive = error_directives if response.status_code in (
                502, 503, 504, 507
            ) else public_directives
            patch_cache_control(response, **directive)

        return response
