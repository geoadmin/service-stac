import logging
from datetime import datetime
from time import mktime
from wsgiref.handlers import format_date_time

from django.conf import settings

from storages.backends.s3boto3 import S3Boto3Storage

from stac_api.utils import get_s3_cache_control_value

logger = logging.getLogger(__name__)


class S3Storage(S3Boto3Storage):
    # pylint: disable=abstract-method
    # pylint: disable=no-member

    def get_object_parameters(self, name):
        """
        Returns a dictionary that is passed to file upload. Override this
        method to adjust this on a per-object basis to set e.g ContentDisposition.

        Args:
            name: string
                file name

        Returns:
            Parameters from AWS_S3_OBJECT_PARAMETERS plus the file sha256 checksum as MetaData
        """
        params = self.object_parameters.copy()

        if 'Metadata' not in params:
            params['Metadata'] = {}
        params['Metadata']['sha256'] = getattr(self, '_tmp_sha256', None)

        if 'CacheControl' in params:
            logger.warning(
                'Global cache-control header for S3 storage will be overwritten for %s', name
            )
        params["CacheControl"] = get_s3_cache_control_value(
            getattr(self, '_tmp_update_interval', -1)
        )

        stamp = mktime(datetime.now().timetuple())
        params['Expires'] = format_date_time(stamp + settings.STORAGE_ASSETS_CACHE_SECONDS)

        return params
