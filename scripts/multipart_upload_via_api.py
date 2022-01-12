import os
import hashlib
from base64 import b64encode
import argparse
from hashlib import md5

import requests
import multihash


def b64_md5(data):
    '''Return the Base64 encoded MD5 digest of the given data

    Args:
        data: string
            input data

    Returns:
        string - base64 encoded MD5 digest of data
    '''
    return b64encode(md5(data).digest()).decode('utf-8')


def get_args():
    parser = argparse.ArgumentParser(
        description="Utility script for uploading large asset files as a multipart upload " \
            "using the STAC API."
    )
    parser.add_argument(
        "env",
        choices=['localhost', 'DEV', 'INT', 'PROD'],
        help="Environment to be used: localhost, DEV, INT or PROD"
    )
    parser.add_argument("collection", help="Name of the asset's collection")
    parser.add_argument("item", help="Name of the asset's item")
    parser.add_argument("asset", help="Name of the asset to be uploaded")
    parser.add_argument("filepath", help="Local path of the asset file to be uploaded")
    parser.add_argument(
        "--part-size",
        type=int,
        default=250,
        help="Size of the file parts in MB [Integer, default: 250 MB]"
    )

    args = parser.parse_args()

    return args


def main():

    # parsing the args and defining variables
    args = get_args()

    scheme = 'https'

    if args.env == "localhost":
        hostname = "http://127.0.0.1:8000"
    elif args.env == "DEV":
        hostname = "sys-data.dev.bgdi.ch"
    elif args.env == "INT":
        hostname = "sys-data.int.bgdi.ch"
    else:
        hostname = "data.geo.admin.ch"

    collection = args.collection
    item = args.item
    asset = args.asset
    asset_path = f'collections/{collection}/items/{item}/assets/{asset}'
    user = os.environ.get('STAC_USER')
    password = os.environ.get('STAC_PASSWORD')
    asset_file_name = args.filepath
    part_size = args.part_size * 1024**2

    sha256 = hashlib.sha256()
    md5_parts = []
    with open(asset_file_name, 'rb') as fd:
        while True:
            data = fd.read(part_size)
            if data == b"" or data == "":
                break
            sha256.update(data)
            md5_parts.append({'part_number': len(md5_parts) + 1, 'md5': b64_md5(data)})
    checksum_multihash = multihash.to_hex_string(multihash.encode(sha256.digest(), 'sha2-256'))
    md5 = b64encode(hashlib.md5(data).digest()).decode('utf-8')

    # 1. Create a multipart upload
    print("First POST request for creating the multipart upload...")
    response = requests.post(
        f"{scheme}://{hostname}/api/stac/v0.9/{asset_path}/uploads",
        auth=(user, password),
        json={
            "number_parts": len(md5_parts),
            "md5_parts": md5_parts,
            "checksum:multihash": checksum_multihash
        }
    )
    if response.status_code == 401 and 'Invalid username/password.' in response.json(
    )["description"]["detail"]:
        raise Exception(
            "WARNING: Either no or the wrong credentials (username/password) were provided!"
        )
    upload_id = response.json()['upload_id']

    # 2. Upload the part using the presigned url
    print("Uploading the parts...")
    parts = []
    number_of_parts = len(response.json()['urls'])

    with open(asset_file_name, 'rb') as fd:

        for url in response.json()['urls']:
            print(f"Uploading part {url['part']} of {number_of_parts}")
            data = fd.read(part_size)
            retry = 3
            while retry:
                response = requests.put(
                    url['url'],
                    data=data,
                    headers={'Content-MD5': md5_parts[url['part'] - 1]["md5"]}
                )
                if response.status_code == 200:
                    parts.append({'etag': response.headers['ETag'], 'part_number': url['part']})
                    retry = 0
                else:
                    retry -= 1
                    if retry <= 0:
                        print('Failed to upload part %s' % (url['part']))
                        exit(-1)

    # 3. Complete the upload
    print("Completing the upload...")
    response = requests.post(
        f"{scheme}://{hostname}/api/stac/v0.9/{asset_path}/uploads/{upload_id}/complete",
        auth=(user, password),
        json={'parts': parts}
    )

    print("Done!")


if __name__ == '__main__':
    main()