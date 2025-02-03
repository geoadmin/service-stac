import urllib
from django.conf import settings
from botocore.exceptions import ClientError
import logging
from stac_api.models.item import Asset

from django.core.management.base import BaseCommand, CommandParser
from stac_api.utils import CommandHandler, get_s3_client, select_s3_bucket

logger = logging.getLogger(__name__)


class CreatePresignedPost(CommandHandler):

    def create(self):
        asset = Asset.objects.get(name=self.options['asset_id'])

        expires_in = 600
        selected_bucket = select_s3_bucket(asset.item.collection.name)
        bucket = settings.AWS_SETTINGS[selected_bucket.name]['S3_BUCKET_NAME']
        s3 = get_s3_client(selected_bucket)
        object_key = asset.get_asset_path()
        print(f"Creating presigned post url for {object_key} on {bucket}")
        try:
            # response = s3.generate_presigned_post(
            #     Bucket=bucket, Key=object_key, ExpiresIn=expires_in
            # )
            response = s3.generate_presigned_url(
                'put_object', Params={
                    'Bucket': bucket, "Key": object_key
                }, ExpiresIn=expires_in
            )
            print(response)
            # url = response["url"]
            # query_str = urllib.parse.urlencode(response['fields'])
            # print(f"{url}?{query_str}")

        except ClientError:
            logger.exception(
                "Couldn't get a presigned POST URL for bucket '%s' and object '%s'",
                bucket,
                object_key,
            )
            raise


class Command(BaseCommand):

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)

        parser.add_argument('asset_id')

    def handle(self, *args, **options):
        CreatePresignedPost(self, options).create()
