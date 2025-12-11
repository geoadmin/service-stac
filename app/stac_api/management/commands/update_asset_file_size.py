import logging

from django.core.management.base import CommandParser

from stac_api.models.collection import CollectionAsset
from stac_api.models.item import Asset
from stac_api.utils import CustomBaseCommand

# increase the log level so boto3 doesn't spam the output
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)


class Command(CustomBaseCommand):
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
        self.print('Running command to update file size')

        asset_limit = self.options['count']

        asset_qs = Asset.objects.filter(file_size=0, is_external=False)
        total_asset_count = asset_qs.count()
        assets = asset_qs.all()[:asset_limit]

        self.print(f'Update file size for {len(assets)} assets out of {total_asset_count}')

        for asset in assets:
            try:
                file_size = asset.file.size
                asset.file_size = file_size
                asset.save()
                print(".", end="", flush=True)
            # ValueError is when the asset.file isn't even set
            except (FileNotFoundError, ValueError):
                # We set file_size to None to indicate that this asset couldn't be
                # found on the bucket. That way the script won't get stuck with the
                # same 100 inexistent assets on one hand and we'll be able to
                # produce a list of missing files on the other hand.
                # Beware! Attention! Due to the current implementation of DynamicStorageFileFields,
                # it is possible that an attempt is made to read the file size from the wrong
                # bucket.
                asset.file_size = None
                asset.save()
                print("_", end="", flush=True)
                self.print_error('file %s could not be found', asset.file)

        collection_asset_qs = CollectionAsset.objects.filter(file_size=0)
        total_asset_count = collection_asset_qs.count()
        collection_assets = collection_asset_qs.all()[:asset_limit]

        self.print(
            f"Update file size for {len(collection_assets)} collection assets out of "
            f"{total_asset_count}"
        )

        for collection_asset in collection_assets:
            try:
                collection_asset.file_size = collection_asset.file.size
                collection_asset.save()
                print(".", end="", flush=True)
            # ValueError is when the asset.file isn't even set
            except (FileNotFoundError, ValueError):
                # We set file_size to None to indicate that this asset couldn't be
                # found on the bucket. That way the script won't get stuck with the
                # same 100 inexistent assets on one hand and we'll be able to
                # produce a list of missing files on the other hand.
                # Beware! Attention! Due to the current implementation of DynamicStorageFileFields,
                # it is possible that an attempt is made to read the file size from the wrong
                # bucket.
                collection_asset.file_size = None
                collection_asset.save()
                self.print_error('file %s could not be found', collection_asset.file)

        self.print_success('Update completed')
