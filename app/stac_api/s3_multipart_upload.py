import logging
import time
from datetime import datetime
from datetime import timedelta

from botocore.exceptions import ClientError
from botocore.exceptions import ParamValidationError
from multihash import to_hex_string

from django.conf import settings

from rest_framework.exceptions import ValidationError

from stac_api.utils import get_s3_client
from stac_api.utils import isoformat
from stac_api.utils import parse_multihash
from stac_api.utils import utc_aware

logger = logging.getLogger(__name__)


class MultipartUpload:
    '''Multi part upload class

    Implement the Multipart upload with S3 backend.
    '''

    def __init__(self):
        self.s3 = get_s3_client()

    def create_multipart_upload(self, key, asset, checksum_multihash):
        '''Create a multi part upload on the backend

        Args:
            key: string
                key on the S3 backend for which we want to create a multipart upload
            asset: Asset
                Asset metadata model associated with the S3 backend key
            checksum_multihash: string
                Checksum multihash (must be sha256) of the future file to be uploaded

        Returns: string
            Upload Id of the created multipart upload
        '''
        sha256 = to_hex_string(parse_multihash(checksum_multihash).digest)
        try:
            response = self.s3.create_multipart_upload(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=key,
                Metadata={'sha256': sha256},
                CacheControl=', '.join([
                    'public', f'max-age={settings.STORAGE_ASSETS_CACHE_SECONDS}'
                ]),
                ContentType=asset.media_type
            )
        except ClientError as error:
            logger.error(
                'Failed to create multipart upload: %s',
                error,
                extra={
                    'collection': asset.item.collection.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    's3_error': error.response
                }
            )
            raise
        logger.info(
            'S3 Multipart upload successfully created: upload_id=%s',
            response['UploadId'],
            extra={
                's3_response': response, 'upload_id': response['UploadId'], 'asset': asset.name
            }
        )
        return response['UploadId']

    def create_presigned_url(self, key, asset, part, upload_id):
        '''Create a presigned url for an upload part on the backend

        Args:
            key: string
                key on the S3 backend for which we want to create a presigned url upload part
            asset: Asset
                Asset metadata model associated with the S3 backend key
            part: int
                Part number for which to create a presigned url for upload part
            upload_id: string
                Upload ID for which to create a presigned url

        Returns: [string, int, datetime]
            List [url, part, expires]
        '''
        expires = utc_aware(
            datetime.utcnow() + timedelta(seconds=settings.AWS_PRESIGNED_URL_EXPIRES)
        )
        try:
            url = self.s3.generate_presigned_url(
                'upload_part',
                Params={
                    'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                    'Key': key,
                    'UploadId': upload_id,
                    'PartNumber': part
                },
                ExpiresIn=settings.AWS_PRESIGNED_URL_EXPIRES,
                HttpMethod='PUT'
            )
        except ClientError as error:
            logger.error(
                'Failed to create presigned url for upload part: %s',
                error,
                extra={
                    'collection': asset.item.collection.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'upload_id': upload_id,
                    's3_error': error.response
                }
            )
            raise
        logger.info(
            'Presigned url %s for %s part %s with expires %s created',
            url,
            key,
            part,
            isoformat(expires),
            extra={
                'upload_id': upload_id, 'asset': asset.name
            }
        )
        return [url, part, expires]

    def complete_multipart_upload(self, key, asset, parts, upload_id):
        '''Complete a multipart upload on the backend

        Args:
            key: string
                key on the S3 backend for which we want to complete the multipart upload
            asset: Asset
                Asset metadata model associated with the S3 backend key
            parts: [{'Etag': string, 'Part': int}]
                List of Etag and part number to use for the completion
            upload_id: string
                Upload ID

        Raises:
            ValidationError: when the parts are not valid
        '''
        logger.debug(
            'Sending complete mutlipart upload for %s',
            key,
            extra={
                'parts': parts, 'upload_id': upload_id, 'asset': asset.name
            },
        )
        try:
            started = time.time()
            response = self.s3.complete_multipart_upload(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=key,
                MultipartUpload={'Parts': parts},
                UploadId=upload_id
            )
        except ParamValidationError as error:
            ended = time.time() - started
            logger.error(
                'Failed to complete multipart upload: %s',
                error,
                extra={
                    'collection': asset.item.collection.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'upload_id': upload_id,
                    's3_error': error,
                    'duration': ended
                }
            )
            raise
        except ClientError as error:
            ended = time.time() - started
            logger.error(
                'Failed to complete multipart upload: %s',
                error,
                extra={
                    'collection': asset.item.collection.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'upload_id': upload_id,
                    's3_error': error.response,
                    'duration': ended
                }
            )
            raise ValidationError(str(error), code='invalid') from None
        ended = time.time() - started
        if 'Location' in response:
            logger.info(
                'Successfully complete a multipart asset upload: %s',
                response['Location'],
                extra={
                    's3_response': response,
                    'duration': ended,
                    'upload_id': upload_id,
                    'asset': asset.name
                },
            )
            return
        logger.error(
            'Failed to complete a multipart asset upload',
            extra={
                's3_response': response,
                'duration': ended,
                'upload_id': upload_id,
                'asset': asset.name
            },
        )
        raise ValueError(response)

    def abort_multipart_upload(self, key, asset, upload_id):
        '''Abort a multipart upload on the backend

        Args:
            key: string
                key on the S3 backend for which we want to complete the multipart upload
            asset: Asset
                Asset metadata model associated with the S3 backend key
            upload_id: string
                Upload ID
        '''
        logger.debug(
            'Aborting mutlipart upload for %s...',
            key,
            extra={
                'upload_id': upload_id, 'asset': asset.name
            },
        )
        try:
            started = time.time()
            response = self.s3.abort_multipart_upload(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key, UploadId=upload_id
            )
        except ClientError as error:
            ended = time.time() - started
            logger.error(
                'Failed to abort multipart upload: %s',
                error,
                extra={
                    'collection': asset.item.collection.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'upload_id': upload_id,
                    's3_error': error.response,
                    'duration': ended
                }
            )
            raise
        ended = time.time() - started
        logger.info(
            'Successfully aborted a multipart asset upload: %s',
            key,
            extra={
                's3_response': response,
                'duration': ended,
                'upload_id': upload_id,
                'asset': asset.name
            },
        )
