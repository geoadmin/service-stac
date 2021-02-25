import logging
import sys

logger = logging.getLogger(__name__)


class ExceptionLoggingMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        # NOTE: this process_exception is not called for REST Framework endpoints. For those
        # the exceptions handling and logging is done within stac_api.apps.custom_exception_handler
        extra = {"request": request}
        logger.critical(repr(exception), extra=extra, exc_info=sys.exc_info())
