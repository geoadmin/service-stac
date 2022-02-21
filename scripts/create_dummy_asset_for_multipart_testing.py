# This will create a dummy asset file for testing the multipart upload via the API.

import argparse
import gzip
import os


def get_args():
    parser = argparse.ArgumentParser(
        description="This script creates a dummy asset file for testing the multipart upload via " \
            "the API. File size of the original file is specified via argument. The file will be " \
                "zipped afterwards, hence the final file size is smaller than the specified size " \
                    "of the unzipped dummy asset file."
    )
    parser.add_argument(
        "size",
        type=int,
        default=20,
        help="Size of the unzipped dummy asset file in MB [Integer, default: 20 MB]"
    )

    args = parser.parse_args()

    return args


def main():
    # parsing the args and defining variables
    args = get_args()

    FILE_SIZE = args.size * 1024**2
    with open("dummy_asset_for_multipart_testing.zip", "wb") as dummy_file:
        # compresslevel=1 will result in a low compression level, hence large .zip file size, which is
        # desired for testing here.
        dummy_file.write(gzip.compress(os.urandom(FILE_SIZE), compresslevel=1))


if __name__ == '__main__':
    main()