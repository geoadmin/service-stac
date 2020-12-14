from moto import mock_s3

from config.settings import *

print("starting mock in settings")
s3mock = mock_s3()
s3mock.start()
