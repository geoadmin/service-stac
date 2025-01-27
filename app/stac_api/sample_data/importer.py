import glob
import json
import logging
import os

from dateutil.parser import isoparse

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.uploadedfile import SimpleUploadedFile

from stac_api.models.general import Asset
from stac_api.models.general import Collection
from stac_api.models.general import CollectionLink
from stac_api.models.general import Item
from stac_api.models.general import Provider

# path definition relative to the directory that contains manage.py
DATADIR = settings.BASE_DIR / 'app/stac_api/management/sample_data/'
logger = logging.getLogger(__name__)


def create_provider(collection, provider_data):
    logger.debug('Create provider %s', provider_data['name'])
    provider, created = Provider.objects.get_or_create(
        collection=collection,
        name=provider_data['name'],
        defaults={
            "description": provider_data.get('description', None),
            "url": provider_data.get('url', None),
            "roles": provider_data.get('roles', [])
        }
    )
    provider.full_clean()
    provider.save()
    return provider


def create_collection_link(collection, link_data):
    link, created = CollectionLink.objects.get_or_create(
        collection=collection,
        rel=link_data["rel"],
        defaults={
            "href": link_data["href"],
            "link_type": link_data.get("type", None),
            "title": link_data.get("title", None),
        }
    )
    link.full_clean()
    link.save()
    return link


def import_collection(collection_dir):
    """Import a whole collection folder

    The collection_dir has to be structured as follows
    ```
    <collection_name>/
       |- items/
            |- <item1_name>.json
            |- <item2_name>.json
       |- collection.json
    ```
    """

    if not collection_dir.is_dir():
        raise ValueError(f'Input is not a directory: {collection_dir}')
    logger.debug('Trying to import collection dir: %s', collection_dir)
    collection_json = os.path.join(collection_dir, "collection.json")
    with open(collection_json, encoding="utf-8") as collection_file:
        collection_data = json.load(collection_file)
    try:
        collection = parse_collection(collection_data)
    except FileNotFoundError as error:
        logger.error(error)
        raise

    # loop over all the items inside the current collection folder
    for item in glob.iglob(os.path.join(collection_dir, "items", "*.json")):
        logger.debug('Trying to import item: %s, in collection: %s', item, collection)
        import_item(item)

    return collection


def parse_collection(collection_data):
    # fist we care about the required properties
    collection, created = Collection.objects.get_or_create(
        name=collection_data["id"],
        defaults={
            "description": collection_data["description"],
            "license": collection_data["license"]
        },
    )

    # Create providers
    for provider_data in collection_data.get("providers", []):
        provider = create_provider(collection, provider_data)

    collection.title = collection_data.get("title", None)
    collection.full_clean()
    collection.save()

    for link in collection_data.get("links", []):
        if link['rel'] in ['self', 'root', 'parent', 'items', 'collection']:
            logger.info('Ignore collection auto link rel=%s href=%s', link['rel'], link['href'])
            continue
        create_collection_link(collection, link)

    return collection


def import_item(item_path):
    with open(item_path, encoding="utf-8") as item_file:
        item_data = json.load(item_file)
        item = parse_item(item_data)
        return item


def get_property_datetime(item_data, key):
    if key in item_data['properties']:
        return isoparse(item_data['properties'][key])
    return None


def parse_item(item_data):
    collection = Collection.objects.get(name=item_data["collection"])
    geometry = GEOSGeometry(json.dumps(item_data["geometry"]))
    if not geometry.valid:
        raise ValueError(f'Invalid geometry in item {item_data["id"]}: {geometry.valid_reason}')
    item, created = Item.objects.get_or_create(
        name=item_data["id"],
        collection=collection,
        defaults={
            'geometry': geometry,
            'properties_datetime': get_property_datetime(item_data, 'datetime'),
            'properties_start_datetime': get_property_datetime(item_data, 'start_datetime'),
            'properties_end_datetime': get_property_datetime(item_data, 'end_datetime'),
        }
    )

    if 'title' in item_data['properties']:
        item.title = item_data['properties']['title']
    item.full_clean()
    item.save()

    for asset_name, asset_data in item_data["assets"].items():
        parse_asset(item, asset_name, asset_data)
    return item


def parse_asset(item, asset_name, asset_data):
    asset, created = Asset.objects.get_or_create(
        item=item,
        name=asset_name,
        defaults={
            "file": SimpleUploadedFile(asset_name, b'Asset dummy content'),
            "media_type": asset_data["type"],
            "eo_gsd": asset_data.get("gsd", None),
            "proj_epsg": asset_data.get("proj:epsg", None),
            "geoadmin_lang": asset_data.get("geoadmin:lang", None),
            "geoadmin_variant": asset_data.get("geoadmin:variant", None),
        }
    )
    return asset
