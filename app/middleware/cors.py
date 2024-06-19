import logging

from django.conf import settings

logger = logging.getLogger(__name__)

STAC_BASE = settings.STAC_BASE


class CORSHeadersMiddleware:
    '''Middleware that adds appropriate CORS headers.

    CORS has only effect on browser applications (e.g. STAC browser),
    not on other systems. Therefore we only allow GET and HEAD requests
    on all endpoints except /search.
    '''

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.
        response['Access-Control-Allow-Origin'] = '*'
        # Access-Control-Allow-Methods:
        allow_methods = ['GET', 'HEAD']
        # For /search we allow POST as well
        if request.path in (f'/{STAC_BASE}/v0.9/search', f'/{STAC_BASE}/v1/search'):
            allow_methods.append('POST')
        response['Access-Control-Allow-Methods'] = ','.join(allow_methods)
        response['Access-Control-Allow-Headers'] = 'Content-Type,Accept'

        return response
