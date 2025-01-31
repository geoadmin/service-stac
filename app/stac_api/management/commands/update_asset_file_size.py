import logging

from botocore.exceptions import ClientError

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandParser

from stac_api.models.collection import CollectionAsset
from stac_api.models.item import Asset
from stac_api.utils import CommandHandler
from stac_api.utils import get_s3_client
from stac_api.utils import select_s3_bucket
from stac_api.views.upload import SharedAssetUploadBase

logger = logging.getLogger(__name__)

# increase the log level so boto3 doesn't spam the output
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)


class Handler(CommandHandler):

    def update(self):
        self.print_success('Running command to update file size')

        asset_limit = self.options['count']

        asset_qs = Asset.objects.filter(file_size=0, is_external=False)
        total_asset_count = asset_qs.count()
        assets = asset_qs.all()[:asset_limit]

        self.print_success(f'Update file size for {len(assets)} assets out of {total_asset_count}')

        for asset in assets:
            try:
                file_size = asset.file.size
                asset.file_size = file_size
                asset.save()
                print(".", end="", flush=True)
            except FileNotFoundError:
                # We set file_size to None to indicate that this asset couldn't be
                # found on the bucket. That way the script won't get stuck with the
                # same 100 inexistent assets on one hand and we'll be able to
                # produce a list of missing files on the other hand
                asset.file_size = None
                asset.save()
                print("_", end="", flush=True)
                logger.error(
                    'file size could not be read from s3 bucket [%s] for asset %s', bucket, key
                )
        print()

        collection_asset_qs = CollectionAsset.objects.filter(file_size=0)
        total_asset_count = collection_asset_qs.count()
        collection_assets = collection_asset_qs.all()[:asset_limit]

        self.print_success(
            f"Update file size for {len(collection_assets)} collection assets out of "
            f"{total_asset_count}"
        )

        for collection_asset in collection_assets:
            try:
                collection_asset.file_size = collection_asset.file.size
                collection_asset.save()
                print(".", end="", flush=True)
            except FileNotFoundError:
                # We set file_size to None to indicate that this asset couldn't be
                # found on the bucket. That way the script won't get stuck with the
                # same 100 inexistent assets on one hand and we'll be able to
                # produce a list of missing files on the other hand
                collection_asset.file_size = None
                collection_asset.save()
                print("_", end="", flush=True)
                logger.error(
                    'file size could not be read from s3 bucket [%s] for collection asset %s'
                )

        print()
        self.print_success('Update completed')


class Command(BaseCommand):
    help = """Requests the file size of every asset / collection asset from the s3 bucket and
        updates the value in the database"""

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            '-c',
            '--count',
            help="The amount of assets to process at once",
            required=True,
            type=int
        )

    def handle(self, *args, **options):
        Handler(self, options).update()
