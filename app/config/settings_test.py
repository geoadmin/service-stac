"""
    The special test settings file ensures that the moto
    mock is imported before anything else and can mock the boto3
    stuff right from the beginning.
    Note: Don't change the order of the first three lines, nothing
    else must be imported before the s3mock is started!

    isort:skip_file
"""
# pylint: disable=wildcard-import,unused-wildcard-import,wrong-import-position,wrong-import-order
from moto import mock_s3

s3mock = mock_s3()
s3mock.start()

from config.settings import *

AWS_SETTINGS = {
    'legacy': {
        "access_type": "key",
        "ACCESS_KEY_ID": 'my-key',
        "SECRET_ACCESS_KEY": 'my-key',
        "DEFAULT_ACL": 'public-read',
        "S3_REGION_NAME": 'wonderland',
        "S3_ENDPOINT_URL": None,
        "S3_CUSTOM_DOMAIN": 'testserver',
        "STORAGE_BUCKET_NAME": 'legacy',
        "S3_SIGNATURE_VERSION": "s3v4"
    },
    "managed": {
        "access_type": "service_account",
        "DEFAULT_ACL": 'public-read',
        "ROLE_ARN": 'Arnold',
        "S3_REGION_NAME": 'wonderland',
        "S3_ENDPOINT_URL": None,
        "S3_CUSTOM_DOMAIN": 'testserver',
        "STORAGE_BUCKET_NAME": 'managed',
        "S3_SIGNATURE_VERSION": "s3v4"
    }
}
