import logging
from urllib import parse

from django.conf import settings
from django.core.handlers.wsgi import WSGIRequest
from django.utils.translation import gettext_lazy as _

from rest_framework import pagination
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.utils.urls import remove_query_param
from rest_framework.utils.urls import replace_query_param

from stac_api.utils import get_query_params
from stac_api.utils import remove_query_params

logger = logging.getLogger(__name__)


def update_links_with_pagination(data, previous_url, next_url):
    '''Update the links dictionary with the previous and next link if needed

    When no 'links' is present in data it is added even if there is no previous and/or next link
    to add.

    Args:
        data: dict
            data dictionary
        previous_url: string
            previous url
        next_url: string
            next url

    Returns: tuple(dict, None|dict, None|dict)
        Tuple (data, previous_link, next_link)
    '''
    links = []
    previous_link = None
    next_link = None
    if next_url is not None:
        next_link = {'rel': 'next', 'href': next_url}
        links.append(next_link)
    if previous_url is not None:
        previous_link = {'rel': 'previous', 'href': previous_url}
        links.append(previous_link)

    if 'links' not in data:
        data.update({'links': links})
    elif links:
        data['links'] += links
    return data, previous_link, next_link


def validate_page_size(size_string, max_page_size, log_extra=None):
    '''Parse and validate page size

    Args:
        size_string: string
            page size in string
        max_page_size: int
            max page size allowed
        log_extra: dict
            extra to add to the log message in case of error

    Returns: int
        Page size parsed

    Raises:
        ValidationError: if page size is invalid
    '''
    try:
        page_size = int(size_string)
    except ValueError as error:
        logger.error(
            'Invalid query parameter limit=%s: must be an integer', size_string, extra=log_extra
        )
        raise ValidationError(
            _('invalid limit query parameter: must be an integer'),
            code='limit'
        ) from None

    if page_size <= 0:
        logger.error(
            'Invalid query parameter limit=%d: negative number not allowed',
            page_size,
            extra=log_extra
        )
        raise ValidationError(
            _('limit query parameter too small, must be in range 1..%d') % (max_page_size),
            code='limit'
        )
    if max_page_size and page_size > max_page_size:
        logger.error(
            'Invalid query parameter limit=%d: number bigger than the max size of %d',
            page_size,
            max_page_size,
            extra=log_extra
        )
        raise ValidationError(
            _('limit query parameter too big, must be in range 1..%d') % (max_page_size),
            code='limit'
        )
    return page_size


def validate_offset(offset_string, log_extra=None):
    '''Parse and validate offset

    Args:
        offset_string: string
            page size in string
        log_extra: dict
            extra to add to the log message in case of error

    Returns: int
        Offset parsed

    Raises:
        ValidationError: if offset is invalid
    '''
    try:
        offset = int(offset_string)
    except ValueError as error:
        logger.error(
            'Invalid query parameter offset=%s: must be an integer', offset_string, extra=log_extra
        )
        raise ValidationError(
            _('invalid offset query parameter: must be an integer'),
            code='invalid'
        ) from None

    if offset < 0:
        logger.error(
            'Invalid query parameter offset=%d: negative number not allowed',
            offset,
            extra=log_extra
        )
        raise ValidationError(
            _('offset query parameter too small, must be positive'),
            code='invalid'
        )
    return offset


class CursorPagination(pagination.CursorPagination):
    '''Default pagination for all endpoints
    '''
    ordering = 'id'
    page_size_query_param = 'limit'
    max_page_size = settings.REST_FRAMEWORK['PAGE_SIZE_LIMIT']

    def get_paginated_response(self, data):
        update_links_with_pagination(data, self.get_previous_link(), self.get_next_link())
        return Response(data)

    def get_page_size(self, request):
        # Overwrite the default implementation about the page size as this one
        # don't validate the query parameter, its simply correct it if it is not valid
        # here we want to return a 400 BAD REQUEST when the provided page size is invalid.
        return validate_page_size(
            request.query_params.get(self.page_size_query_param, str(self.page_size)),
            self.max_page_size,
            log_extra={'request': request}
        )


class GetPostCursorPagination(CursorPagination):
    '''Pagination to be used for the GET/POST /search endpoint where the
    pagination is either in query or in payload depending on the method.
    '''

    def get_paginated_response(self, data, request=None):  # pylint: disable=arguments-differ
        data, previous_link, next_link = update_links_with_pagination(
            data, self.get_previous_link(), self.get_next_link()
        )
        self.patch_link(previous_link, request)
        self.patch_link(next_link, request)
        return Response(data)

    def get_page_size(self, request):
        if request.method == 'POST':
            # For POST method the page size, aka `limit` parameter is in the body and not in the
            # URL query
            return validate_page_size(
                request.data.get(self.page_size_query_param, str(self.page_size)),
                self.max_page_size,
                log_extra={'request': request}
            )
        return super().get_page_size(request)

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


class ExtApiPagination:
    """
    A limit/offset based style pagination for external API (e.g. S3)

    http://api.example.org/accounts/?limit=100
    http://api.example.org/accounts/?offset=400&limit=100
    """
    default_limit = settings.REST_FRAMEWORK['PAGE_SIZE']
    max_limit = settings.REST_FRAMEWORK['PAGE_SIZE_LIMIT']
    limit_query_param = 'limit'
    offset_query_param = 'offset'

    def get_pagination_config(self, request):
        # pylint: disable=attribute-defined-outside-init
        self.request = request
        self.limit = self.get_limit(request)
        self.offset = self.get_offset(request)
        return self.limit, self.offset

    def get_next_link(self):
        next_url = self.request.build_absolute_uri()
        next_url = replace_query_param(next_url, self.limit_query_param, self.limit)

        offset = self.offset + self.limit
        return replace_query_param(next_url, self.offset_query_param, offset)

    def get_previous_link(self):
        if self.offset <= 0:
            return None

        previous_url = self.request.build_absolute_uri()
        previous_url = replace_query_param(previous_url, self.limit_query_param, self.limit)

        if self.offset - self.limit <= 0:
            previous_url = remove_query_param(previous_url, self.offset_query_param)
        else:
            offset = self.offset - self.limit
            previous_url = replace_query_param(previous_url, self.offset_query_param, offset)
        return previous_url

    def get_paginated_response(self, data, has_next):
        update_links_with_pagination(
            data, self.get_previous_link(), self.get_next_link() if has_next else None
        )
        return Response(data)

    def get_limit(self, request):
        return validate_page_size(
            request.query_params.get(self.limit_query_param, str(self.default_limit)),
            self.max_limit,
            log_extra={'request': request}
        )

    def get_offset(self, request):
        return validate_offset(
            request.query_params.get(self.offset_query_param, str(0)),
            log_extra={'request': request}
        )
