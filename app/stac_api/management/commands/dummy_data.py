import datetime
import logging
import random
import string
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from datetime import timedelta

from dateutil.parser import isoparse

from django.contrib.gis.geos import Polygon
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import Item
from stac_api.utils import CommandHandler
from stac_api.validators import MEDIA_TYPES

logger = logging.getLogger(__name__)

# Min/Max extent (roughly) of CH in LV95
XMIN = 2570000
XMAX = 2746000
YMIN = 1130000
YMAX = 1252000

MIN_DATETIME = isoparse('1970-01-01T00:00:01Z')
MAX_DATETIME = isoparse('2020-12-31T23:59:10Z')

NAME_PREFIX = 'test-dummy-data'


def random_datetime(start, end):
    """Generate a random datetime between `start` and `end`"""
    return start + datetime.timedelta(
        # Get a random amount of seconds between `start` and `end`
        seconds=random.randint(0, int((end - start).total_seconds())),
    )


class DummyDataHandler(CommandHandler):

    def clean(self):
        self.print_warning('Deleting all collections starting with "%s"...', NAME_PREFIX)
        collections = map(
            lambda obj: obj['name'],
            Collection.objects.filter(name__startswith=NAME_PREFIX).values('name')
        )
        errors = 0
        if self.options['parallel_collections'] > 1:
            with ThreadPoolExecutor(max_workers=self.options['parallel_collections']) as executor:
                futures_to_id = {
                    executor.submit(self.delete_collection, collection_name): collection_name
                    for collection_name in collections
                }
                for future in as_completed(futures_to_id):
                    collection_name = futures_to_id[future]
                    try:
                        future.result()
                    except Exception as exc:  # pylint: disable=broad-except
                        self.print_error(
                            'Delete collection %s generated an exception: %s', collection_name, exc
                        )
                        errors += 1
        else:
            for collection_name in collections:
                self.delete_collection(collection_name)

        self.print_success('Done')

    def populate(self):
        start = time.time()
        if self.options['collections'].isdecimal():
            collections = [
                f'{NAME_PREFIX}-collection-{x}' for x in range(int(self.options['collections']))
            ]
        else:
            collections = [
                f'{NAME_PREFIX}-{name}' for name in self.options['collections'].split(',')
            ]
        items = [f'{NAME_PREFIX}-item-{x}' for x in range(self.options['items'])]
        assets = [f'{NAME_PREFIX}-asset-{x}' for x in range(self.options['assets'])]

        self.print_warning(
            "Creating %d collections, %d items, %d assets...",
            len(collections),
            len(items),
            len(assets)
        )

        errors = 0
        if self.options['parallel_collections'] > 1:
            with ThreadPoolExecutor(max_workers=self.options['parallel_collections']) as executor:
                futures_to_id = {
                    executor.submit(self.create_collection, collection_id, items, assets):
                        collection_id for collection_id in collections
                }
                for future in as_completed(futures_to_id):
                    collection_id = futures_to_id[future]
                    try:
                        future.result()
                    except Exception as exc:  # pylint: disable=broad-except
                        self.print_error(
                            'Create collection %s generated an exception: %s', collection_id, exc
                        )
                        errors += 1
        else:
            for collection_id in collections:
                self.create_collection(collection_id, items, assets)

        duration = time.time() - start
        if errors:
            self.print_error('Populate of collection failed with %d errors', errors)
        else:
            self.print_success(
                "Created %d collections, %d items, %d assets in %s",
                len(collections),
                len(items),
                len(assets),
                str(timedelta(seconds=duration))
            )

    def delete_collection(self, collection_name):
        items = map(
            lambda obj: obj['name'],
            Item.objects.filter(collection__name=collection_name).values('name')
        )
        errors = 0
        if self.options['parallel_items'] > 1:
            with ThreadPoolExecutor(max_workers=self.options['parallel_items']) as executor:
                futures_to_name = {
                    executor.submit(self.delete_item, collection_name, item_name): item_name
                    for item_name in items
                }
                for future in as_completed(futures_to_name):
                    item_name = futures_to_name[future]
                    try:
                        future.result()
                    except Exception as exc:  # pylint: disable=broad-except
                        self.print_error(
                            'Delete item %s/%s generated an exception: %s',
                            collection_name,
                            item_name,
                            exc
                        )
                        errors += 1

            if errors:
                raise Exception(  # pylint: disable=broad-exception-raised
                    f'Failed to delete collection\'s {collection_name} items: {errors} errors'
                )
        else:
            for item_name in items:
                self.delete_item(collection_name, item_name)

        Collection.objects.get(name=collection_name).delete()
        self.print('collection %s deleted', collection_name)

    def create_collection(self, collection_id, items, assets):
        collection, _ = Collection.objects.get_or_create(
            name=collection_id,
            defaults={
                'description': 'This is a description',
                'license': 'test',
                # Title should start by a `A` in order to be on top of the list
                # for E2E pagination tests
                'title': 'A Collection for Test'
            }
        )

        errors = 0
        if self.options['parallel_items'] > 1:
            with ThreadPoolExecutor(max_workers=self.options['parallel_items']) as executor:
                futures_to_id = {
                    executor.submit(self.create_item, collection, item_id, assets): item_id
                    for item_id in items
                }
                for future in as_completed(futures_to_id):
                    item_id = futures_to_id[future]
                    try:
                        future.result()
                    except Exception as exc:  # pylint: disable=broad-except
                        self.print_error(
                            'Create item %s/%s generated an exception: %s',
                            collection_id,
                            item_id,
                            exc
                        )
                        errors += 1

            if errors:
                raise Exception(f'Failed to create collection\'s items: {errors} errors')  # pylint: disable=broad-exception-raised
        else:
            for item_id in items:
                self.create_item(collection, item_id, assets)

        self.print('collection %s created', collection_id)

    def delete_item(self, collection_name, item_name):
        for asset in Asset.objects.filter(
            item__collection__name=collection_name, item__name=item_name
        ):
            asset.delete()
        Item.objects.get(collection__name=collection_name, name=item_name).delete()

    def create_item(self, collection, item_id, assets):
        xmin = random.randint(XMIN, XMAX)
        ymin = random.randint(YMIN, YMAX)
        geo = Polygon.from_bbox((xmin, ymin, xmin + 1000, ymin + 1000))
        geo.srid = 2056
        geo.transform(4326, clone=False)

        item, _ = Item.objects.get_or_create(
            collection=collection,
            name=item_id,
            defaults={
                'properties_datetime': random_datetime(MIN_DATETIME, MAX_DATETIME),
                'properties_title': f"This is my Item Title: {item_id}",
                'geometry': geo
            }
        )

        for asset_id in assets:
            self.create_asset(item, asset_id)

        self.print('Item %s/%s created', collection.name, item_id, level=3)

    def create_asset(self, item, asset_id):
        media_type = random.choice(MEDIA_TYPES)
        asset, _ = Asset.objects.get_or_create(
            item=item,
            name=f'{asset_id}{random.choice(media_type[2])}',
            defaults={
                'title': f'This is my asset title: {asset_id}',
                'description': f"This is a detail description of the asset {asset_id}.",
                'eo_gsd': random.choice([2, 2.5, 5, 10]),
                'geoadmin_lang': random.choice(['de', 'fr', 'it', 'rm', 'en']),
                'geoadmin_variant': random.choice(['var1', 'var2', 'var3']),
                'proj_epsg': random.choice([2056, 4326, 21781]),
                'media_type': media_type[0],
                'file': SimpleUploadedFile(
                    f'{item.collection.name}/{item.name}/{asset_id}',
                    ''.join(random.choices(
                        string.ascii_uppercase + string.digits, k=16))
                        .encode('utf-8')
                )
            }
        )
        self.print('Asset %s/%s/%s created', item.collection.name, item.name, asset_id, level=3)


class Command(BaseCommand):
    help = """Manage dummy data for performance testing.

    The command populates the database by default with
    30 collections, 300 items per collection and 2 assets per item.
    Number of collections, items and assets can be changed.

    The generated data is randomized where necessary, i.e. the field
    that are also likely to be queried.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            type=str,
            choices=['populate', 'clean'],
            default='populate',
            help='Define the action to be performed, either "populate" (default) to create '
            'dummy data or "clean" to delete it',
        )

        parser.add_argument(
            '--collections',
            type=str,
            default='30',
            help="Number of collections to create (default 30), or alternatively a comma separated "
            f"list of collection names to create (a common prefix '{NAME_PREFIX}' is added to "
            "these names)"
        )

        parser.add_argument(
            '--items',
            type=int,
            default=300,
            help="Number of items per collection to create (default 300)"
        )

        parser.add_argument(
            '--assets', type=int, default=2, help="Number of assets per item to create (default 2)"
        )

        parser.add_argument(
            '--parallel-collections',
            type=int,
            default=1,
            help="Number of collection created in parallel (default 1)"
        )

        parser.add_argument(
            '--parallel-items',
            type=int,
            default=5,
            help="Number of items created in parallel (default 5)"
        )

    def handle(self, *args, **options):
        handler = DummyDataHandler(self, options)

        if options['action'] == 'clean':
            handler.clean()
        elif options['action'] == 'populate':
            handler.populate()
