import logging
from datetime import datetime
from time import mktime
from wsgiref.handlers import format_date_time

from django.conf import settings

from storages.backends.s3boto3 import S3Boto3Storage

from stac_api.utils import get_s3_cache_control_value

logger = logging.getLogger(__name__)


class BaseS3Storage(S3Boto3Storage):
    # pylint: disable=abstract-method

    object_sha256 = None
    update_interval = -1
    asset_content_type = None

    access_key = None
    secret_key = None
    bucket_name = None
    endpoint_url = None

    def __init__(self):
        if (not self.access_key or not self.secret_key or not self.bucket_name):
            raise Exception("Implement this in subclass")
        super().__init__()
        self.object_sha256 = None
        self.update_interval = -1
        self.asset_content_type = None

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
        params = super().get_object_parameters(name)

        # Set the content-type from the assets metadata
        if self.asset_content_type is None:
            raise ValueError(f'Missing content-type for asset {name}')
        params["ContentType"] = self.asset_content_type

        if 'Metadata' not in params:
            params['Metadata'] = {}
        if self.object_sha256 is None:
            raise ValueError(f'Missing asset object sha256 for {name}')
        params['Metadata']['sha256'] = self.object_sha256

        if 'CacheControl' in params:
            logger.warning(
                'Global cache-control header for S3 storage will be overwritten for %s', name
            )
        params["CacheControl"] = get_s3_cache_control_value(self.update_interval)

        stamp = mktime(datetime.now().timetuple())
        params['Expires'] = format_date_time(stamp + settings.STORAGE_ASSETS_CACHE_SECONDS)

        return params


class LegacyS3Storage(BaseS3Storage):
    # pylint: disable=abstract-method

    def __init__(self):
        # specifying the configuration as we're not using the
        # environment variables / globals settings (due two having two
        # buckets to access)
        self.access_key = settings.AWS_SETTINGS['legacy']['ACCESS_KEY_ID']
        self.secret_key = settings.AWS_SETTINGS['legacy']['SECRET_ACCESS_KEY']
        self.bucket_name = settings.AWS_SETTINGS['legacy']['S3_BUCKET_NAME']
        self.endpoint_url = settings.AWS_SETTINGS['legacy']['S3_ENDPOINT_URL']

        super().__init__()


class ManagedS3Storage(BaseS3Storage):
    # pylint: disable=abstract-method

    def __init__(self):
        # specifying the configuration as we're not using the
        # environment variables / globals settings (due two having two
        # buckets to access)
        self.access_key = settings.AWS_SETTINGS['managed']['ACCESS_KEY_ID']
        self.secret_key = settings.AWS_SETTINGS['managed']['SECRET_ACCESS_KEY']
        self.bucket_name = settings.AWS_SETTINGS['managed']['S3_BUCKET_NAME']
        self.endpoint_url = settings.AWS_SETTINGS['managed']['S3_ENDPOINT_URL']

        super().__init__()
