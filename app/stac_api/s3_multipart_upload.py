import logging
import time
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from botocore.exceptions import ClientError
from botocore.exceptions import ParamValidationError
from multihash import to_hex_string

from django.conf import settings

from rest_framework import serializers

from stac_api.exceptions import UploadNotInProgressError
from stac_api.models.collection import CollectionAsset
from stac_api.models.item import Asset
from stac_api.utils import AVAILABLE_S3_BUCKETS
from stac_api.utils import get_s3_cache_control_value
from stac_api.utils import get_s3_client
from stac_api.utils import isoformat
from stac_api.utils import parse_multihash

logger = logging.getLogger(__name__)


class MultipartUpload:
    '''Multi part upload class

    Implement the Multipart upload with S3 backend.
    '''

    def __init__(self, s3_bucket: AVAILABLE_S3_BUCKETS = AVAILABLE_S3_BUCKETS.legacy):
        self.s3_bucket = s3_bucket
        self.s3 = get_s3_client(self.s3_bucket)

    @property
    def settings(self):
        config = settings.AWS_SETTINGS[self.s3_bucket.name]
        return config

    def list_multipart_uploads(self, key=None, limit=100, start=None):
        '''List all in progress multipart uploads

        Args:
            key: string | None
                Only list for a specific asset file
            limit: int
                Limit the output number of result
            start: str
                Upload ID start marker for retrieving the next results

        Returns: ([], bool, string, string)
            Returns a tuple (uploads, has_next, next_key, next_upload_id)
        '''

        kwargs = {'Bucket': self.settings['S3_BUCKET_NAME'], 'MaxUploads': limit}
        if key is not None:
            kwargs['KeyMarker'] = key
        if start is not None:
            kwargs['UploadIdMarker'] = start
        response = self.call_s3_api(self.s3.list_multipart_uploads, **kwargs)
        return (
            response.get('Uploads', []),
            response.get('IsTruncated', False),
            response.get('NextKeyMarker', None),
            response.get('NextUploadIdMarker', None),
        )

    def log_extra(self, asset: Asset | CollectionAsset, upload_id=None, parts=None):
        if isinstance(asset, Asset):
            log_extra = {
                'collection': asset.item.collection.name,
                'item': asset.item.name,
                'asset': asset.name,
            }
        else:
            log_extra = {
                'collection': asset.collection.name,
                'asset': asset.name,
            }
        if upload_id is not None:
            log_extra['upload_id'] = upload_id
        if parts is not None:
            log_extra['parts'] = parts
        return log_extra

    def create_multipart_upload(
        self, key, asset, checksum_multihash, cache_control_header, content_encoding
    ):
        '''Create a multi part upload on the backend

        Args:
            key: string
                key on the S3 backend for which we want to create a multipart upload
            asset: Asset
                Asset metadata model associated with the S3 backend key
            checksum_multihash: string
                Checksum multihash (must be sha256) of the future file to be uploaded
            cache_control_header: string
                Cache control header to set on the uploaded data on S3. Note if empty, then use
                default cache control value.
            content_encoding: str
                Content Encoding header to set to the asset. If empty no content-encoding
                is set

        Returns: string
            Upload Id of the created multipart upload
        '''
        sha256 = to_hex_string(parse_multihash(checksum_multihash).digest)
        extra_params = {}
        if content_encoding:
            extra_params['ContentEncoding'] = content_encoding

        response = self.call_s3_api(
            self.s3.create_multipart_upload,
            Bucket=self.settings['S3_BUCKET_NAME'],
            Key=key,
            Metadata={'sha256': sha256},
            CacheControl=get_s3_cache_control_value(cache_control_header),
            ContentType=asset.media_type,
            **extra_params,
            log_extra=self.log_extra(asset)
        )
        logger.info(
            'S3 Multipart upload successfully created: upload_id=%s',
            response['UploadId'],
            extra={
                's3_response': response, 'upload_id': response['UploadId'], 'asset': asset.name
            }
        )
        return response['UploadId']

    def create_presigned_url(self, key, asset, part, upload_id, part_md5):
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
            part_md5: string
                base64 MD5 digest of the part

        Returns: dict(string, int, datetime)
            Dict {'url': string, 'part': int, 'expires': datetime}
        '''
        expires = datetime.now(UTC) + timedelta(seconds=settings.AWS_PRESIGNED_URL_EXPIRES)
        params = {
            'Bucket': self.settings['S3_BUCKET_NAME'],
            'Key': key,
            'UploadId': upload_id,
            'PartNumber': part,
            'ContentMD5': part_md5,
        }
        url = self.call_s3_api(
            self.s3.generate_presigned_url,
            'upload_part',
            Params=params,
            ExpiresIn=settings.AWS_PRESIGNED_URL_EXPIRES,
            HttpMethod='PUT',
            log_extra=self.log_extra(asset, upload_id=upload_id)
        )

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
        return {'url': url, 'part': part, 'expires': expires}

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
        Returns:
            Size of upload in bytes
        '''

        try:
            response = self.call_s3_api(
                self.s3.complete_multipart_upload,
                Bucket=self.settings['S3_BUCKET_NAME'],
                Key=key,
                MultipartUpload={'Parts': parts},
                UploadId=upload_id,
                log_extra=self.log_extra(asset, upload_id=upload_id, parts=parts)
            )
        except ClientError as error:
            raise serializers.ValidationError(str(error)) from None
        except KeyError as error:
            # If we try to complete an upload that has already be completed, then a KeyError is
            # generated. Although this should never happens because we check the state of the upload
            # via the DB before sending the complete command to S3, it could happend if the previous
            # complete was abruptly aborted (e.g. server crash), leaving the S3 completed without
            # updating the DB.
            logger.error(
                "Failed to complete upload, probably because the upload was not in progress: %s",
                error
            )
            raise UploadNotInProgressError() from None

        if 'Location' not in response:
            logger.error(
                'Failed to complete a multipart asset upload',
                extra={
                    's3_response': response, 'upload_id': upload_id, 'asset': asset.name
                },
            )
            raise ValueError(response)

        try:
            return self.s3.head_object(Bucket=self.settings['S3_BUCKET_NAME'],
                                       Key=key)['ContentLength']
        except ClientError:
            logger.error('file size could not be read from s3 bucket')
            return 0

    def abort_multipart_upload(self, key, asset, upload_id):
        '''Abort a multipart upload on the backend

        Args:
            key: string
                key on the S3 backend for which we want to abort the multipart upload
            asset: Asset
                Asset metadata model associated with the S3 backend key
            upload_id: string
                Upload ID
        '''
        self.call_s3_api(
            self.s3.abort_multipart_upload,
            Bucket=self.settings['S3_BUCKET_NAME'],
            Key=key,
            UploadId=upload_id,
            log_extra={
                'upload_id': upload_id, 'asset': asset.name
            }
        )

    def list_upload_parts(self, key, asset, upload_id, limit, offset):
        '''List all actual part uploaded for a multipart upload

        Args:
            key: string
                key on the S3 backend for which we want to complete the multipart upload
            asset: Asset
                Asset metadata model associated with the S3 backend key
            upload_id: string
                Upload ID
            limit: int
                Limit the number of result (for pagination)
            offset: int
                Start offset of the result list (for pagination)
        Returns: dict
            AWS S3 list parts answer

        Raises:
            ValueError: if AWS S3 return an HTTP Error code
            ClientError: any S3 client error
        '''
        response = self.call_s3_api(
            self.s3.list_parts,
            Bucket=self.settings['S3_BUCKET_NAME'],
            Key=key,
            UploadId=upload_id,
            MaxParts=limit,
            PartNumberMarker=offset,
            log_extra=self.log_extra(asset, upload_id=upload_id)
        )
        return response, response.get('IsTruncated', False)

    def call_s3_api(self, func, *args, **kwargs):
        '''Wrap a S3 API call with logging and generic error handling

        Args:
            func: callable
                S3 client method to call
            log_extra: dict
                dictionary to pass as extra to the logger
            *args:
                Argument to pass to the S3 method call
            **kwargs:
                Keyword arguments to pass to the S3 method call

        Response: dict
            S3 client response
        '''
        log_extra = kwargs.pop('log_extra', {})
        logger.debug('Calling S3 %s(%s, %s)', func.__name__, args, kwargs, extra=log_extra)
        time_started = time.time()
        try:
            response = func(*args, **kwargs)
        except (ClientError, ParamValidationError) as error:
            log_extra.update({'duration': time.time() - time_started})
            if isinstance(error, ClientError):
                log_extra.update({'s3_response': error.response})
            logger.error(
                'Failed to call %s(args=%s, kwargs=%s): %s',
                func.__name__,
                args,
                kwargs,
                error,
                extra=log_extra
            )
            raise
        log_extra.update({'duration': time.time() - time_started, 's3_response': response})
        logger.debug(
            'Successfully call %s(args=%s, kwargs=%s)',
            func.__name__,
            args,
            kwargs,
            extra=log_extra
        )

        if (
            'ResponseMetadata' in response and 'HTTPStatusCode' in response['ResponseMetadata'] and
            response['ResponseMetadata']['HTTPStatusCode'] not in [200, 201, 202, 204, 206]
        ):
            log_extra.update({'s3_response': response})
            logger.error(
                'S3 call %s(%s. %s) returned an error code: HTTP %d',
                func.__name__,
                args,
                kwargs,
                response['ResponseMetadata']['HTTPStatusCode'],
                extra=log_extra
            )
            raise ValueError(f"S3 HTTP {response['ResponseMetadata']['HTTPStatusCode']}")

        return response
