import logging
import time
import traceback

from django.http import HttpResponse
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class RequestResponseLoggingMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        logger.info("request", extra={"request": request})
        start = time.time()

        response = self.get_response(request)

        extra = {
            "request": request,
            "response": {
                "code": response.status_code, "headers": dict(response.items())
            },
            "duration": time.time() - start
        }

        # Not all response types have a 'content' attribute,
        # HttpResponse and JSONResponse sure have
        # (e.g. WhiteNoiseFileResponse doesn't)
        if isinstance(response, (HttpResponse, JsonResponse)):
            extra["response"]["content"] = str(response.content)[:200]

        logger.info("request-response", extra=extra)
        # Code to be executed for each request/response after
        # the view is called.

        return response


class ExceptionLoggingMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        return response

    def process_exception(self, request, exception):
        extra = {
            "request": request, "exception": repr(exception), "traceback": traceback.format_exc()
        }
        logger.critical(repr(exception), extra=extra)
