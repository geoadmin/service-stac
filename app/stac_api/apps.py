import logging
import sys

import django.core.exceptions
from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from rest_framework import pagination
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


class CursorPagination(pagination.CursorPagination):
    ordering = 'id'
    page_size_query_param = 'limit'
    max_page_size = settings.REST_FRAMEWORK['PAGE_SIZE_LIMIT']

    def get_paginated_response(self, data):
        links = []
        next_page = self.get_next_link()
        previous_page = self.get_previous_link()
        if next_page is not None:
            links.append({'rel': 'next', 'href': next_page})
        if previous_page is not None:
            links.append({'rel': 'previous', 'href': previous_page})

        if 'links' not in data and not links:
            data.update({'links': []})
        elif 'links' not in data and links:
            data.update({'links': [links]})
        elif links:
            data['links'] += links
        return Response(data)

    def get_page_size(self, request):
        # Overwrite the default implementation about the page size as this one
        # don't validate the query parameter, its simply correct it if it is not valid
        # here we want to return a 400 BAD REQUEST when the provided page size is invalid.

        # POST 'limit' param has a higher priority than GET
        if self.page_size_query_param in request.data:
            integer_string = request.data[self.page_size_query_param]
        else:
            integer_string = request.query_params.get(self.page_size_query_param, self.page_size)

        try:
            page_size = int(integer_string)
        except ValueError as error:
            logger.error(
                'Invalid query parameter limit=%s: must be an integer',
                integer_string,
                extra={'request': request}
            )
            raise ValidationError(
                _('invalid limit query parameter: must be an integer'),
                code='limit'
            )

        if page_size <= 0:
            logger.error(
                'Invalid query parameter limit=%d: negative number not allowed',
                page_size,
                extra={'request': request}
            )
            raise ValidationError(
                _('limit query parameter to small, must be in range 1..%d') % (self.max_page_size),
                code='limit'
            )
        if self.max_page_size and page_size > self.max_page_size:
            logger.error(
                'Invalid query parameter limit=%d: number bigger than the max size of %d',
                page_size,
                self.max_page_size,
                extra={'request': request}
            )
            raise ValidationError(
                _('limit query parameter to big, must be in range 1..%d') % (self.max_page_size),
                code='limit'
            )

        return page_size


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
        if context['request']._request.method.upper() in ["PATCH", "POST", "PUT"]:  # pylint: disable=protected-access
            extra = {
                "request": context['request']._request,  # pylint: disable=protected-access
                "requestPayload":
                    context['request'].data  # pylint: disable=protected-access
            }
        else:
            extra = {"request": context['request']._request}  # pylint: disable=protected-access
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
