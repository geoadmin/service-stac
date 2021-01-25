import logging
from urllib.parse import urlparse

from django.conf import settings
from django.utils.cache import add_never_cache_headers
from django.utils.cache import patch_cache_control
from django.utils.cache import patch_response_headers

logger = logging.getLogger(__name__)


class CacheHeadersMiddleware:
    '''Middleware that adds appropriate cache headers to GET and HEAD methods.

    NOTE: /checker and /get-token endpoints are marked as never cache.
    '''

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        if request.path in ['/checker', '/get-token']:
            # never cache the /checker and /get-token endpoints.
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
            patch_cache_control(response, public=True)

        return response
