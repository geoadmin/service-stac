import logging
import sys

import django.core.exceptions
from django.apps import AppConfig
from django.conf import settings

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class StacApiConfig(AppConfig):
    name = 'stac_api'

    def ready(self):
        # signals have to be imported here so that the @register
        # hooks are executed and signal handlers are active
        # https://docs.djangoproject.com/en/3.1/topics/signals/#django.dispatch.receiver
        import stac_api.signals  # pylint: disable=import-outside-toplevel, unused-import


def custom_exception_handler(exc, context):
    # NOTE: this exception handler is only called for REST Framework endpoints. Other endpoints
    # exception are handled via middleware.exception.
    if isinstance(exc, django.core.exceptions.ValidationError):
        # Translate django ValidationError to Rest Framework ValidationError,
        # this is required because some validation cannot be done in the Rest
        # framework serializer but must be left to the model, like for instance
        # the Item properties datetimes dependencies during a partial update.
        message = exc.message
        if exc.params:
            message %= exc.params
        exc = ValidationError(exc.message, exc.code)

    # Then call REST framework's default exception handler, to get the standard error response.
    response = exception_handler(exc, context)

    if response is not None:
        # pylint: disable=protected-access
        extra = {
            "request": context['request']._request,
            "request.query": context['request']._request.GET.urlencode()
        }

        if (
            context['request']._request.method.upper() in ["PATCH", "POST", "PUT"] and
            'application/json' in context['request']._request.headers['content-type'].lower()
        ):
            extra["request.payload"] = context['request'].data

        logger.error("Response %s: %s", response.status_code, response.data, extra=extra)
        response.data = {'code': response.status_code, 'description': response.data}
        return response

    # If we don't have a response that's means that we have an unhandled exception that needs to
    # return a 500. We need to log the exception here as it might not be re-raised.
    extra = {"request": context['request']._request}  # pylint: disable=protected-access
    logger.critical(repr(exc), extra=extra, exc_info=sys.exc_info())

    if settings.DEBUG and not settings.DEBUG_PROPAGATE_API_EXCEPTIONS:
        # Other exceptions are left to Django to handle in DEBUG mode, this allow django
        # to set a nice HTML output with backtrace when DEBUG_PROPAGATE_EXCEPTIONS is false
        # With DEBUG_PROPAGATE_API_EXCEPTIONS with can disable this behavior for testing purpose
        return None

    # In production make sure to always return a proper REST Framework response, either a json or an
    # html response.
    return Response({'code': 500, 'description': repr(exc)}, status=500)
