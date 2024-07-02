import hashlib
import logging
import random
import uuid
from io import BytesIO

from django.conf import settings
from django.core.management.base import BaseCommand

from stac_api.utils import CommandHandler
from stac_api.utils import get_s3_resource
from stac_api.utils import get_sha256_multihash
from stac_api.validators import MEDIA_TYPES

logger = logging.getLogger(__name__)

PREFIX = 'dummy-obj-'


class DummyAssetHandler(CommandHandler):

    def clean(self):
        self.print_warning("Deleting all assets with prefix %s on S3...", PREFIX)
        s3 = get_s3_resource()
        obj_iter = s3.Bucket(settings.AWS_SETTINGS['legacy']['STORAGE_BUCKET_NAME']
                            ).objects.filter(Prefix=PREFIX)
        for obj in obj_iter:
            obj.delete()
        self.print_success('Done')

    def upload(self):
        number_of_assets = (
            self.options['collections'] * self.options['items'] * self.options['assets']
        )
        self.print_warning("Uploading %s assets on S3...", number_of_assets)
        self.print('-' * 100, level=2)
        s3 = get_s3_resource()
        for collection_id in map(
            lambda i: f'{PREFIX}collection-{i}', range(1, self.options['collections'] + 1)
        ):
            for item_id in map(lambda i: f'{PREFIX}item-{i}', range(1, self.options['items'] + 1)):
                for asset_id in map(
                    lambda i: f'{PREFIX}asset-{i}', range(1, self.options['assets'] + 1)
                ):
                    if self.options['assets'] == 1:
                        media_extension = '.txt'
                    else:
                        media_extension = random.choice(random.choice(MEDIA_TYPES)[2])

                    file = f'{collection_id}/{item_id}/{asset_id}{media_extension}'
                    obj = s3.Object(settings.AWS_SETTINGS['legacy']['STORAGE_BUCKET_NAME'], file)
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
                    self.print('%s,%s', file, get_sha256_multihash(content), level=2)
        self.print('-' * 100, level=2)
        self.print_success('Done')


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

    def handle(self, *args, **options):
        handler = DummyAssetHandler(self, options)
        if options['action'] == 'clean':
            handler.clean()
        elif options['action'] == 'upload':
            handler.upload()
