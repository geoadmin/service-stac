import logging
from urllib import parse

from django.conf import settings
from django.core.handlers.wsgi import WSGIRequest
from django.utils.translation import gettext_lazy as _

from rest_framework import pagination
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from stac_api.utils import get_query_params
from stac_api.utils import remove_query_params

logger = logging.getLogger(__name__)


class CursorPagination(pagination.CursorPagination):
    ordering = 'id'
    page_size_query_param = 'limit'
    max_page_size = settings.REST_FRAMEWORK['PAGE_SIZE_LIMIT']

    def get_next_link(self, request=None):  # pylint: disable=arguments-differ
        next_page = super().get_next_link()
        if next_page:
            return {'rel': 'next', 'href': next_page}
        return None

    def get_previous_link(self, request=None):  # pylint: disable=arguments-differ
        previous_page = super().get_previous_link()
        if previous_page:
            return {'rel': 'previous', 'href': previous_page}
        return None

    def get_paginated_response(self, data, request=None):  # pylint: disable=arguments-differ
        links = []
        next_link = self.get_next_link(request)
        previous_link = self.get_previous_link(request)
        if next_link is not None:
            links.append(next_link)
        if previous_link is not None:
            links.append(previous_link)

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

        integer_string = self.get_raw_page_size(request)

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
            ) from None

        if page_size <= 0:
            logger.error(
                'Invalid query parameter limit=%d: negative number not allowed',
                page_size,
                extra={'request': request}
            )
            raise ValidationError(
                _('limit query parameter too small, must be in range 1..%d') % (self.max_page_size),
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
                _('limit query parameter too big, must be in range 1..%d') % (self.max_page_size),
                code='limit'
            )

        return page_size

    def get_raw_page_size(self, request):
        return request.query_params.get(self.page_size_query_param, str(self.page_size))


class GetPostCursorPagination(CursorPagination):

    def get_raw_page_size(self, request):
        if request.method == 'POST':
            # For POST method the page size, aka `limit` parameter is in the body and not in the
            # URL query
            return request.data.get(self.page_size_query_param, str(self.page_size))
        return super().get_raw_page_size(request)

    def decode_cursor(self, request):
        if request.method == 'POST':
            # Patched the cursor in the url query from POST payload
            cursor_encoded = request.data.get(self.cursor_query_param)
            if cursor_encoded:
                # Here we need to patch the request with the cursor. The original
                # decode_cursor() method is taking the cursor from the URL query
                # that's why we create a new request object being a copy of the
                # original one plus the cursor as URL query. We need to do this
                # copy because request objects are immutable.
                environ = request.environ.copy()
                environ['QUERY_STRING'] += parse.urlencode(
                    {self.cursor_query_param: cursor_encoded},
                    doseq=True,
                )
                request = Request(WSGIRequest(environ))
        return super().decode_cursor(request)

    def get_next_link(self, request=None):
        next_link = super().get_next_link(request)
        return self.patch_link(next_link, request)

    def get_previous_link(self, request=None):
        previous_link = super().get_previous_link(request)
        return self.patch_link(previous_link, request)

    def patch_link(self, link, request):
        if link and request and request.method == 'POST':
            cursor, limit = get_query_params(
                link['href'], [self.cursor_query_param, self.page_size_query_param]
            )
            if cursor or limit:
                link['href'] = remove_query_params(
                    link['href'],
                    [
                        self.page_size_query_param if limit else None,
                        self.cursor_query_param if cursor else None
                    ]
                )
            body = {}
            if limit:
                body['limit'] = limit[0]
            if cursor:
                body['cursor'] = cursor[0]
            link.update({'method': 'POST', 'merge': True, 'body': body})
        return link
