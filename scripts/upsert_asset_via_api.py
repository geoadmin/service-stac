import os
import argparse

import requests


def get_args():
    parser = argparse.ArgumentParser(
        description="Utility script for creating a new asset via STAC API. This needs to be done " \
            "first, in order to be able to do a multipart upload of the asset file for example."
    )
    parser.add_argument("env", choices=["localhost", "DEV", "INT", "PROD"])
    parser.add_argument("collection", help="Name of the asset's collection")
    parser.add_argument("item", help="Name of the asset's item")
    parser.add_argument("asset", help="Name of the asset to be created/updated")
    parser.add_argument("--title", help="Asset's title")
    parser.add_argument("--description", help="Asset's description")
    parser.add_argument("type", help="Media type of the asset")
    parser.add_argument("--geoadmin_variant", help="Product variant")
    parser.add_argument(
        "--geoadmin_lang", help="Product language", choices=["de"
                                                             "it"
                                                             "fr"
                                                             "rm"
                                                             "en"]
    )
    parser.add_argument("--proj_epsg", help="EPSG code", type=int)
    parser.add_argument("--eo_gsd", help="Ground sample distance", type=float)

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
    title = args.title
    description = args.description
    type = args.type
    geoadmin_variant = args.geoadmin_variant
    geoadmin_lang = args.geoadmin_lang
    proj_epsg = args.proj_epsg
    eo_gsd = args.eo_gsd

    asset_path = f'collections/{collection}/items/{item}/assets/{asset}'
    user = os.environ.get('STAC_USER')
    password = os.environ.get('STAC_PASSWORD')

    print(f"Creating/updating asset {asset}")
    response = requests.put(
        f"{scheme}://{hostname}/api/stac/v0.9/{asset_path}",
        auth=(user, password),
        json={
            "title": title,
            "description": description,
            "type": type,
            "geoadmin:variant": geoadmin_variant,
            "geoadmin:lang": geoadmin_lang,
            "proj:epsg": proj_epsg,
            "eo:gsd": eo_gsd,
            "id": asset
        }
    )
    if response.status_code == 401 and 'Invalid username/password.' in response.json(
    )["description"]["detail"]:
        raise Exception(
            "WARNING: Either no or the wrong credentials (username/password) were provided!"
        )

    print("Done!")


if __name__ == '__main__':
    main()
