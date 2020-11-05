import os
import logging
import json
import pprint

from django.contrib.gis.geos import GEOSGeometry

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import Keyword
from stac_api.models import Provider
from django.core.management.base import BaseCommand
from django.conf import settings

# from django.core.management.base import CommandError

# path definiton relative to the directory that contains manage.py
DATADIR = settings.BASE_DIR / 'app/stac_api/management/sample_data/'
logger = logging.getLogger(__name__)


def create_provider():
    pass

def create_collection_link(collection, link):
    # Hier noch Fehler abfangen Index und Key, darauf achten, dass einige Properties
    # allenfalls nicht vorhanden sind und das auch ok ist, weil sie optional sind.
    link, created = CollectionLink.objects.get_or_create(
        collection=collection,
        rel=link["rel"],
        defaults={
        "href": link["href"],
        "link_type": link.get("type", None),
        "title": link.get("title", None),
        }
    )
    link.save()


def create_keyword():
    pass



def import_collection(collection_dir):
    collection_json = os.path.join(collection_dir, "collection.json")
    with open(collection_json) as collection_file:
        collection_data = json.load(collection_file)
        collection = parse_collection(collection_data)
    return collection


def parse_collection(collection_data):
    pprint.pprint(collection_data)
    print(type(collection_data))

    # fist we care about the required properties
    collection, created = Collection.objects.get_or_create(
        collection_name=collection_data["id"], defaults={
            "description": collection_data["description"],
            "collection_name": collection_data["id"],
            "license": collection_data["license"]
        }
    )

    # if "itemType" in collection_data:
    #     collection.item_type = collection_data["itemType"]

    # if "keywords" in collection_data:

    # if "provider" in collection_data:

    collection.title = collection_data.get("title", None)

    collection.save()

    for link in collection_data.get("links", []):
        create_collection_link(collection, link)

    return collection


def import_item(item_path):
    with open(item_path) as item_file:
        item_data = json.load(item_file)
        item = parse_item(item_data)
    return item


def parse_item(item_data):
    pprint.pprint(item_data)
    collection = Collection.objects.get(
        collection_name=item_data["collection"])
    item, created = Item.objects.get_or_create(
        item_name=item_data["id"], 
        collection=collection,
        defaults={
            # Note that GEOSGeometry needs a json string, not a dict
            "geometry": GEOSGeometry(json.dumps(item_data["geometry"])),
            "properties_datetime": item_data["properties"]["datetime"]
        }
    )
    for asset_name, asset_data in item_data["assets"].items():
        parse_asset(item, asset_name, asset_data)


def parse_asset(item, asset_name, asset_data):
    pprint.pprint(asset_data)
    asset, created = Asset.objects.get_or_create(
        item=item,
        collection=item.collection,
        asset_name=asset_name,
        defaults={
            "checksum_multihash": asset_data["checksum:multihash"],
            "eo_gsd": asset_data.get("eo:gsd", None),
            "proj_epsg": asset_data.get("proj:epsg", None),
            "href": asset_data['href'],
            "media_type": asset_data["type"],
            "geoadmin_lang": asset_data.get("geoadmin:lang", None),
            "geoadmin_variant": asset_data.get("geoadmin:variant", None),
        }
    )


class Command(BaseCommand):
    help = """Populates the local test database with sample data
    
    The sample data has to be located in stac_api/management/sample_data and
    structured as follows
    <collection_name>/
       |- items/
            |- <item1_name>.json
            |- <item2_name>.json
       |- collection.json
    """

    def handle(self, *args, **options):

        # loop over the collection directories inside sample_data
        for collection_dir in os.scandir(DATADIR):

            if collection_dir.is_dir():
                logger.debug('Trying to import collection dir: %s', collection_dir)
                try:
                    collection = import_collection(collection_dir)
                except FileNotFoundError as e:
                    logger.error(e)
                    continue


                # loop over all the items inside the current collection folder
                for item in os.scandir(os.path.join(collection_dir, "items")):
                    if item.is_file():
                        logger.debug('Trying to import item: %s, in collection: %s', item, collection)
                        import_item(item)
                # else:
                #     print("Current collection %s is not defined (no JSON file found).", collection)
                #     logger.debug(
                #         "Current collection %s is not defined (no JSON file found).", collection
                    # )



                # value = {k: second_dict[k] for k, _ in set(
                #     second_dict.items()) - set(first_dict.items())}
