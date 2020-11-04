import os
import logging
import json

from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import Keyword
from stac_api.models import Provider
from django.core.management.base import BaseCommand

# from django.core.management.base import CommandError

# path definiton relative to the directory that contains manage.py
DATADIR = './stac_api/management/sample_data/'
logger = logging.getLogger(__name__)


def create_provider():
    pass

def create_link(links):
    # Hier noch Fehler abfangen Index und Key, darauf achten, dass einige Properties
    # allenfalls nicht vorhanden sind und das auch ok ist, weil sie optional sind.
    for l in links:
        link = CollectionLink.objects.get_or_create(
        collection=collection, defaults={
        "href": link["href"],
        "rel": link["rel"],
        "link_type": link["type"],
        "title"= link["title"],
        }
    )
    link.save()

    return True # wie bei import_collection, im Fehlerfall False)




def create_keyword():
    pass



def import_collection(collection_dir):
    collection_json = os.path.join(collection_dir, "collection.json")
    if os.path.exists(collection_json):
        with open(collection_json) as collection_file:
            collection_data = json.load(collection_file)

            print(collection_data["crs"])

            # fist we care about the required properties
            collection = Collection.objects.get_or_create(
                collection_name=collection_data["id"], defaults={
                "description": collection_data["description"],
                "collection_name": collection_data["id"],
                "license": collection_data["license"],
                "stac_version": collection_data["stac_version"],
                }
                )

            collection.save()

            create_links(collection_data["links")


            # now the optional properties
            if "crs" in collection_data:
                collection.crs=["http://www.opengis.net/def/crs/OGC/1.3/CRS84"]

            if "itemType" in collection_data:
                collection.item_type = collection_data["itemType"]

            if "keywords" in collection_data:

            if "provider" in collection_data:

            if "stac_extensions" in collection_data:
                collection.stac_extension=collection_data["stac_extensions"]

            if "title" in collection_data:
                collection.title=collection_data["title"]

            collection.save()

        return True
    else:
        return False


def import_item(item):
    return


class Command(BaseCommand):
    help = 'Populates the local test database with sample data'

    def handle(self, *args, **options):

        # loop over the collection directories inside sample_data
        for collection in os.scandir(DATADIR):

            if collection.is_dir():
                logger.debug('Current collection: %s', collection)
                success = import_collection(collection)

                if success:
                    # loop over all the items inside the current collection folder
                    for item in os.scandir(os.path.join(collection, "items")):
                        if item.is_file():
                            logger.debug('Current item: %s, in collection: %s', item, collection)
                            import_item(item)
                else:
                    print("Current collection %s is not defined (no JSON file found).", collection)
                    logger.debug(
                        "Current collection %s is not defined (no JSON file found).", collection
                    )
