# this will create a 20 MB dummy asset file for testing the upload via
# the admin GUI.

import os

FILE_SIZE = 20 * 1024**2  # this is 20 MB
with open("20MB_sample_asset_file.zip", "wb") as dummy_file:
    dummy_file.write(os.urandom(FILE_SIZE))
