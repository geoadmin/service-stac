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

AWS_ACCESS_KEY_ID = 'my-key'
AWS_SECRET_ACCESS_KEY = 'my-key'
AWS_DEFAULT_ACL = 'public-read'
AWS_S3_REGION_NAME = 'wonderland'
AWS_S3_ENDPOINT_URL = None
AWS_S3_CUSTOM_DOMAIN = 'testserver'
