import logging
import time

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
        if request.method.upper() in ["PATCH", "POST", "PUT"]:
            extra = {"request": request, "requestPayload": str(request.body[:200])}
        else:
            extra = {"request": request}

        logger.info("Request %s %s", request.method.upper(), request.path, extra=extra)
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
            extra["response"]["payload"] = str(response.content)[:200]

        logger.info("Response %s", response.status_code, extra=extra)
        # Code to be executed for each request/response after
        # the view is called.

        return response
