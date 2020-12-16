"""
    The special test settings file ensures that the moto
    mock is imported before anything else and can mock the boto3
    stuff right from the beginning.
    Note: Don't change the order of the first three lines, nothing
    else must be imported before the s3mock is started!

    isort:skip_file
"""
from moto import mock_s3
s3mock = mock_s3()
s3mock.start()

from config.settings import *  # pylint: disable=wildcard-import,unused-wildcard-import,wrong-import-position

AWS_STORAGE_BUCKET_NAME = 'bigbag'
