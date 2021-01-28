import hashlib
import logging
import random
import uuid
from io import BytesIO

from django.conf import settings
from django.core.management.base import BaseCommand

from stac_api.utils import get_s3_resource
from stac_api.utils import get_sha256_multihash
from stac_api.validators import MEDIA_TYPES

logger = logging.getLogger(__name__)

PREFIX = 'dummy-obj-'


class Command(BaseCommand):
    help = f"""Upload dummy asset file on S3 for testing.

    The command upload dummy asset file with random data on S3 for testing.
    By default only one file is uploaded to
    /{PREFIX}collection-1/{PREFIX}item-1/{PREFIX}asset-1.txt

    Optionally you can create more than one asset on several items and collections.
    If more than one asset is uploaded, then its extension is chosen randomly.

    The asset uploaded is then printed to the console with its checksum:multishash.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            type=str,
            choices=['upload', 'clean'],
            default='upload',
            help='Define the action to be performed, either "upload" (default) to create and '
            'upload dummy asset file or "clean" to delete them',
        )

        parser.add_argument(
            '--collections',
            type=int,
            default=1,
            help="Number of collections to create (default 1)"
        )

        parser.add_argument(
            '--items',
            type=int,
            default=1,
            help="Number of items per collection to create (default 1)"
        )

        parser.add_argument(
            '--assets', type=int, default=1, help="Number of assets per item to create (default 1)"
        )

    def print(self, options, message, level=1):
        if options['verbosity'] >= level:
            self.stdout.write(message)

    def print_warning(self, options, message, level=1):
        if options['verbosity'] >= level:
            self.stdout.write(self.style.WARNING(message))

    def print_success(self, options, message, level=1):
        if options['verbosity'] >= level:
            self.stdout.write(self.style.SUCCESS(message))

    def handle(self, *args, **options):
        s3 = get_s3_resource()
        if options['action'] == 'clean':
            self.print_warning(options, f"Deleting all assets with prefix {PREFIX} on S3...")
            obj_iter = s3.Bucket(settings.AWS_STORAGE_BUCKET_NAME).objects.filter(Prefix=PREFIX)
            for obj in obj_iter:
                obj.delete()
        elif options['action'] == 'upload':
            number_of_assets = options['collections'] * options['items'] * options['assets']
            self.print_warning(options, f"Uploading {number_of_assets} assets on S3...")
            self.print(options, '-' * 100, level=2)
            for collection_id in map(
                lambda i: f'{PREFIX}collection-{i}', range(1, options['collections'] + 1)
            ):
                for item_id in map(lambda i: f'{PREFIX}item-{i}', range(1, options['items'] + 1)):
                    for asset_id in map(
                        lambda i: f'{PREFIX}asset-{i}', range(1, options['assets'] + 1)
                    ):
                        if options['assets'] == 1:
                            media_extension = '.txt'
                        else:
                            media_extension = random.choice(random.choice(MEDIA_TYPES)[2])

                        file = f'{collection_id}/{item_id}/{asset_id}{media_extension}'
                        obj = s3.Object(settings.AWS_STORAGE_BUCKET_NAME, file)
                        content = f'Dummy Asset data: {uuid.uuid4()}'.encode()
                        filelike = BytesIO(content)
                        obj.upload_fileobj(
                            filelike,
                            ExtraArgs={
                                'Metadata': {
                                    'sha256': hashlib.sha256(content).hexdigest()
                                },
                                "CacheControl":
                                    f"max-age={settings.STORAGE_ASSETS_CACHE_SECONDS}, public"
                            }
                        )
                        self.print(options, f'{file},{get_sha256_multihash(content)}', level=2)
        self.print(options, '-' * 100, level=2)
        self.print_success(options, 'Done')
