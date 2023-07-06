import logging

from django.utils.translation import gettext_lazy as _

import rest_framework.exceptions
from rest_framework import status

logger = logging.getLogger(__name__)


class StacAPIException(rest_framework.exceptions.APIException):
    '''STAC API custom exception

    These exception can add additional data to the HTTP response.
    '''

    def __init__(self, detail=None, code=None, data=None):
        super().__init__(detail, code)
        if isinstance(data, dict):
            self.data = data
        elif data:
            self.data = {'data': data}


class UploadNotInProgressError(StacAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _('No upload in progress')
    default_code = 'conflict'


class UploadInProgressError(StacAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _('Upload already in progress')
    default_code = 'conflict'
