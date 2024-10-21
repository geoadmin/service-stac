import logging

from botocore.exceptions import ClientError

from django.conf import settings
from django.core.management.base import BaseCommand

from stac_api.models import Asset
from stac_api.models import CollectionAsset
from stac_api.utils import AVAILABLE_S3_BUCKETS
from stac_api.utils import CommandHandler
from stac_api.utils import get_s3_client
from stac_api.views.upload import SharedAssetUploadBase

# path definition relative to the directory that contains manage.py
DATADIR = settings.BASE_DIR / 'app/stac_api/sample_data/'
logger = logging.getLogger(__name__)


class Handler(CommandHandler):

    def update(self):
        self.print_success('running command to update file size')
        s3 = get_s3_client(AVAILABLE_S3_BUCKETS.legacy)
        bucket = settings.AWS_SETTINGS[AVAILABLE_S3_BUCKETS.legacy.name]['S3_BUCKET_NAME']

        self.print_success('update file size for assets')
        assets = Asset.objects.filter(file_size=0).all()
        for asset in assets:
            key = SharedAssetUploadBase.get_path(None, asset)
            try:
                file_size = s3.head_object(Bucket=bucket, Key=key)['ContentLength']
                asset.file_size = file_size
                asset.save()
            except ClientError:
                logger.error('file size could not be read from s3 bucket for asset %s', key)

        self.print_success('update file size for collection assets')
        collection_assets = CollectionAsset.objects.filter(file_size=0).all()
        for collection_asset in collection_assets:
            key = SharedAssetUploadBase.get_path(None, collection_asset)
            try:
                file_size = s3.head_object(Bucket=bucket, Key=key)['ContentLength']
                collection_asset.file_size = file_size
                collection_asset.save()
            except ClientError:
                logger.error(
                    'file size could not be read from s3 bucket for collection asset %s', key
                )

        self.print_success('Update completed')


class Command(BaseCommand):
    help = """Requests the file size of every asset / collection asset from the s3 bucket and
        updates the value in the database"""

    def handle(self, *args, **options):
        Handler(self, options).update()
