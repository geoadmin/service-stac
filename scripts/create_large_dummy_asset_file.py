# this will create a 60 GB dummy asset file for testing the upload via
# the admin GUI.
LARGE_FILE_SIZE = 60 * 1024**3  # this is 60 GB
with open("xxxxxxl_asset_file.zip", "wb") as dummy_file:
    dummy_file.seek(int(LARGE_FILE_SIZE) - 1)
    dummy_file.write(b"\0")
