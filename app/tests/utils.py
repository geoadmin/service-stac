import functools
import hashlib
import logging
import os
import time
from io import BytesIO

import botocore
from moto import mock_s3

from django.conf import settings
from django.contrib.auth import get_user_model

from stac_api.utils import AVAILABLE_S3_BUCKETS
from stac_api.utils import get_s3_resource
from stac_api.utils import get_sha256_multihash

logger = logging.getLogger(__name__)


def mock_request_from_response(factory, response):
    '''Mock a request from a client response

    This can be used to verify a client response against the manually serialized response data.
    Some serializer require a request context in order to generate links.
    '''
    return factory.get(f'{response.request["PATH_INFO"]}?{response.request["QUERY_STRING"]}')


def get_http_error_description(json_response):
    '''Get the HTTP error description from response
    '''
    return f"{json_response['description'] if 'description' in json_response else ''}"


class S3TestMixin():
    '''Check if object on s3 exists

    This TestCase mixin provides helpers to check whether an
    object exists at a specific location on s3 or not
    '''

    def assertS3ObjectExists(self, path):  # pylint: disable=invalid-name
        s3 = get_s3_resource()

        try:
            s3.Object(settings.AWS_SETTINGS['legacy']['S3_BUCKET_NAME'], path).load()
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == "404":
                # Object Was Not Found
                self.fail("the object was not found at the expected location")
            self.fail(f"object lookup failed for unexpected reason: {error}")

    def assertS3ObjectNotExists(self, path):  # pylint: disable=invalid-name
        s3 = get_s3_resource()
        with self.assertRaises(
            botocore.exceptions.ClientError, msg=f'Object {path} found on S3'
        ) as exception_context:
            s3.Object(settings.AWS_SETTINGS['legacy']['S3_BUCKET_NAME'], path).load()
        error = exception_context.exception
        self.assertEqual(error.response['Error']['Code'], "404")

    def get_s3_object(self, path):
        s3 = get_s3_resource()

        try:
            obj = s3.Object(settings.AWS_SETTINGS['legacy']['S3_BUCKET_NAME'], path)
            obj.load()
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == "404":
                # Object Was Not Found
                self.fail(f"The S3 object {path} was not found at the expected location")
            self.fail(f"The S3 object {path} lookup failed for unexpected reason: {error}")
        return obj

    def assertS3ObjectCacheControl(self, obj, path, max_age=None, no_cache=False):  # pylint: disable=invalid-name
        self.assertNotEqual(obj.cache_control, '', msg=f'S3 object {path} has no cache_control set')
        if no_cache:
            self.assertEqual(
                obj.cache_control, 'max-age=0, no-cache, no-store, must-revalidate, private'
            )
        elif max_age is not None:
            self.assertEqual(obj.cache_control, f'max-age={max_age}, public')

    def assertS3ObjectContentEncoding(self, obj, path, encoding):  # pylint: disable=invalid-name
        self.assertEqual(
            obj.content_encoding,
            encoding,
            msg=f'S3 object {path} has a wrong content_encoding, '
            f'is={obj.content_encoding}, expected={encoding}'
        )

    def assertS3ObjectContentType(self, obj, path, content_type):  # pylint: disable=invalid-name
        self.assertEqual(
            obj.content_type,
            content_type,
            msg=f'S3 object {path} has a wrong content_type, '
            f'is={obj.content_type}, expected={content_type}'
        )

    def assertS3ObjectSha256(self, obj, path, sha256):  # pylint: disable=invalid-name
        self.assertEqual(
            obj.metadata['sha256'],
            sha256,
            msg=f'S3 object {path} has a wrong sha256, '
            f'is={obj.metadata["sha256"]}, expected={sha256}'
        )


def mock_s3_bucket(s3_bucket: AVAILABLE_S3_BUCKETS = AVAILABLE_S3_BUCKETS.legacy):
    '''Mock an S3 bucket

    This functions checks if an S3 bucket exists and create it if not. This
    can be used to mock the bucket for unittest.
    '''
    start = time.time()
    s3 = get_s3_resource(s3_bucket)
    try:
        s3.meta.client.head_bucket(Bucket=settings.AWS_SETTINGS[s3_bucket.name]['S3_BUCKET_NAME'])
    except botocore.exceptions.ClientError as error:
        # If a client error is thrown, then check that it was a 404 error.
        # If it was a 404 error, then the bucket does not exist.
        error_code = error.response['Error']['Code']
        if error_code == '404':
            # We need to create the bucket since this is all in Moto's 'virtual' AWS account
            s3.create_bucket(
                Bucket=settings.AWS_SETTINGS[s3_bucket.name]['S3_BUCKET_NAME'],
                CreateBucketConfiguration={
                    'LocationConstraint': settings.AWS_SETTINGS[s3_bucket.name]['S3_REGION_NAME']
                }
            )
            logger.debug('Mock S3 bucket created in %fs', time.time() - start)
        else:
            raise Exception(  # pylint: disable=broad-exception-raised
                f"Unable to mock the s3 bucket: {error.response['Error']['Message']}"
            ) from error
    logger.debug('Mock S3 bucket in %fs', time.time() - start)


def mock_s3_asset_file(test_function):
    '''Mock S3 Asset file decorator

    This decorator can be used to mock Asset file on S3. This can be used for unittest that want
    to create/update Assets.
    '''

    @mock_s3
    @functools.wraps(test_function)
    def wrapper(*args, **kwargs):
        mock_s3_bucket()
        test_function(*args, **kwargs)

    return wrapper


def upload_file_on_s3(file_path, file, params=None):
    '''Upload a file on S3 using boto3

    Args:
        file_path: string
            file path on S3 (key)
        file: bytes | BytesIO | File
            file to upload
        params: None | dict
            parameters to path to boto3.upload_fileobj() as ExtraArgs
    '''
    s3 = get_s3_resource()
    obj = s3.Object(settings.AWS_SETTINGS['legacy']['S3_BUCKET_NAME'], file_path)
    if isinstance(file, bytes):
        file = BytesIO(file)
    if params is not None:
        extra_args = params
    else:
        extra_args = {
            'Metadata': {
                'sha256': hashlib.sha256(file.read()).hexdigest()
            },
            "CacheControl": f"max-age={settings.STORAGE_ASSETS_CACHE_SECONDS}, public"
        }
    obj.upload_fileobj(file, ExtraArgs=extra_args)


def client_login(client):
    '''Log in the given client

    This creates a dummy user and log the client in. This can be used for unittesting when a
    request requires authorization.

    Args:
        client:
            unittest client for HTTP request
    '''
    username = 'SherlockHolmes'
    password = '221B_BakerStreet'
    superuser = get_user_model().objects.create_superuser(
        username, 'test_e_mail1234@some_fantasy_domainname.com', password
    )
    client.login(username=username, password=password)


def get_auth_headers():
    '''Creates a superuser and returns authentication headers that can be used in conjunction with
    this user.
    '''
    apiuser = get_user_model().objects.create_superuser('apiuser', 'apiuser@example.org', 'apiuser')
    return {"Geoadmin-Username": "apiuser", "Geoadmin-Authenticated": "true"}


class disableLogger:  # pylint: disable=invalid-name
    """Disable temporarily a logger with a with statement

    Args:
        logger_name: str | None
            logger name to disable, by default use the root logger (None)

    Example:
        with disableLogger('stac_api.apps'):
            # the stac_api.apps logger is totally disable within the with statement
            logger = logging.getLogger('stac_api.apps')
            logger.critical('This log will not be printed anywhere')
    """

    def __init__(self, logger_name=None):
        if logger_name:
            self.logger = logging.getLogger(logger_name)
        else:
            self.logger = logging.getLogger()

    def __enter__(self):
        self.logger.disabled = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.disabled = False


def get_file_like_object(size):
    '''Get a random file like object of size with its sha256 checksum

    Args:
        size: int
            size of the file like object to retrieve

    Returns: obj, str
        Random file like object and its sha256 multihash checksum
    '''
    file_like = os.urandom(size)
    checksum_multihash = get_sha256_multihash(file_like)
    return file_like, checksum_multihash
