import functools
import logging
import time

import botocore
from moto import mock_s3

from django.conf import settings
from django.contrib.auth import get_user_model

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
            s3.Object(settings.AWS_STORAGE_BUCKET_NAME, path).load()
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == "404":
                # Object Was Not Found
                self.fail("the object was not found at the expected location")
            self.fail(f"object lookup failed for unexpected reason: {error}")

    def assertS3ObjectNotExists(self, path):  # pylint: disable=invalid-name
        s3 = get_s3_resource()
        with self.assertRaises(botocore.exceptions.ClientError) as exception_context:
            s3.Object(settings.AWS_STORAGE_BUCKET_NAME, path).load()
        error = exception_context.exception
        self.assertEqual(error.response['Error']['Code'], "404")


def mock_s3_bucket():
    '''Mock an S3 bucket

    This functions check if a S3 bucket exists and create it if not. This
    can be used to mock the bucket for unittest.
    '''
    start = time.time()
    s3 = get_s3_resource()
    try:
        s3.meta.client.head_bucket(Bucket=settings.AWS_STORAGE_BUCKET_NAME)
    except botocore.exceptions.ClientError as error:
        # If a client error is thrown, then check that it was a 404 error.
        # If it was a 404 error, then the bucket does not exist.
        error_code = error.response['Error']['Code']
        if error_code == '404':
            # We need to create the bucket since this is all in Moto's 'virtual' AWS account
            s3.create_bucket(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                CreateBucketConfiguration={'LocationConstraint': settings.AWS_S3_REGION_NAME}
            )
            logger.debug('Mock S3 bucket created in %fs', time.time() - start)
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


def mock_requests_asset_file(mocker, asset):
    '''Mock the HEAD request to the Asset file

    When creating/updating an Asset, the serializer verify if the file exists by doing a HEAD
    request to the File on S3. This function mock this request.

    Args:
        mocker:
            python requests mocker.
        asset:
            Asset sample used to create/modify an asset
    '''
    mocker.head(
        f'http://{settings.AWS_S3_CUSTOM_DOMAIN}/{asset["item"].collection.name}/{asset["item"].name}/{asset["name"]}',
        headers={
            'x-amz-meta-sha256': asset.get("checksum_multihash", get_sha256_multihash(b''))[4:]
        }
    )


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
