import datetime
import logging
import random
import string

from dateutil.parser import isoparse

from django.contrib.gis.geos import Polygon
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import Item
from stac_api.validators import MEDIA_TYPES

logger = logging.getLogger(__name__)

# Min/Max extent (roughly) of CH in LV95
XMIN = 2570000
XMAX = 2746000
YMIN = 1130000
YMAX = 1252000

MIN_DATETIME = isoparse('1970-01-01T00:00:01Z')
MAX_DATETIME = isoparse('2020-12-31T23:59:10Z')


def random_datetime(start, end):
    """Generate a random datetime between `start` and `end`"""
    return start + datetime.timedelta(
        # Get a random amount of seconds between `start` and `end`
        seconds=random.randint(0, int((end - start).total_seconds())),
    )


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
            type=int,
            default=30,
            help="Number of collections to create (default 30)"
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

    def handle(self, *args, **options):

        if options['action'] == 'clean':
            Collection.objects.filter(name__startswith='perftest').delete()
        elif options['action'] == 'populate':

            for collection_id in [
                f'perftest-collection-{x}' for x in range(options['collections'])
            ]:
                collection, _ = Collection.objects.get_or_create(
                    name=collection_id,
                    defaults={
                        'description': 'This is a description',
                        'license': 'test',
                        'title': 'Test title'
                    }
                )

                for item_id in [f'perftest-item-{x}' for x in range(options['items'])]:
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
                            'properties_title': "My Title",
                            'geometry': geo
                        }
                    )

                    for asset_id in [f'perftest-asset-{x}' for x in range(options['assets'])]:
                        media_type = random.choice(MEDIA_TYPES)
                        asset, _ = Asset.objects.get_or_create(
                            item=item,
                            name=f'{asset_id}{random.choice(media_type[2])}',
                            defaults={
                                'title': 'my-title',
                                'description': "this an asset",
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
