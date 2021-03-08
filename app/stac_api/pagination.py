import logging

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from rest_framework import pagination
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

logger = logging.getLogger(__name__)


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
