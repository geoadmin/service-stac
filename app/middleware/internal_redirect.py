import logging

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.http import HttpResponseRedirect
from django.middleware.common import CommonMiddleware


class InternalRedirect(HttpResponseRedirect):
    pass


class CommonMiddlewareWithInternalRedirect(CommonMiddleware):
    """
    Same as CommonMiddleware except that when an HTTP redirection should be
    issued, it follows the redirection itself.
    """
    response_redirect_class = InternalRedirect
    logger = logging.getLogger(__name__)

    def get_full_path_with_slash(self, request):
        # CommonMiddleware.get_full_path_with_slash refuses to process methods that
        # may have data associated to them (i.e. DELETE, POST, PUT, PATCH) when
        # DEBUG is True. Instead of reimplementing the method, we temporarily
        # disable DEBUG.
        debug_old_value = settings.DEBUG
        try:
            settings.DEBUG = False
            return super().get_full_path_with_slash(request)
        finally:
            settings.DEBUG = debug_old_value

    def process_response(self, request, response):
        new_response = super().process_response(request, response)
        if not isinstance(new_response, InternalRedirect):
            return new_response

        if request.path_info.endswith('/'):
            self.logger.error(
                'Not redirecting path that already ends with a slash: %s: %s',
                request.path_info,
                request
            )
            return new_response

        # We don't use get_full_path_with_slash here as we only care about the path
        # without the query parametres.
        new_path = '{request.path_info}/'
        self.logger.info('Internal redirect %s -> %s', request.path_info, new_path)
        request.path_info = new_path
        return get_wsgi_application().get_response(request)
