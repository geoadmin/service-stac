import os

from django.conf import settings

from stac_api.models.general import BaseAssetUpload
from stac_api.models.item import Asset
from stac_api.models.item import AssetUpload
from stac_api.s3_multipart_upload import MultipartUpload
from stac_api.utils import AVAILABLE_S3_BUCKETS
from stac_api.utils import CommandHandler
from stac_api.utils import CustomBaseCommand
from stac_api.utils import get_asset_path
from stac_api.utils import get_sha256_multihash


class DummyAssetUploadHandler(CommandHandler):

    def __init__(self, *args, **kwargs):

        # Note: the command is currently just used to be able to manipulate
        # AssetUpload objects, not to actually upload content to a bucket, so
        # the bucket configuration here is just to be able to create a MultipartUpload
        # object.
        s3_bucket = kwargs.pop('s3_bucket', AVAILABLE_S3_BUCKETS.legacy)
        super().__init__(*args, **kwargs)
        self.print_success(
            f"connect MultipartUploader to s3 bucket "
            f"{settings.AWS_SETTINGS[s3_bucket.name]['S3_BUCKET_NAME']}"
        )
        self.uploader = MultipartUpload(s3_bucket)

    def start(self):
        self.print_success(f"Starting upload for {self.options['asset_id']}")
        asset = Asset.objects.filter(name=self.options['asset_id']).first()
        if not asset:
            self.print_error(f"asset with id {self.options['asset_id']} doesn't exist")
            return

        key = get_asset_path(asset.item, asset.name)
        self.print_success(f" -- {key} (with pk {asset.id})")
        size = 1000
        file_like = os.urandom(size)
        checksum_multihash = get_sha256_multihash(file_like)

        upload_id = self.uploader.create_multipart_upload(
            key=key,
            asset=asset,
            checksum_multihash=checksum_multihash,
            cache_control_header="public, max-age=360",
            content_encoding=None
        )
        AssetUpload.objects.get_or_create(
            asset=asset, upload_id=upload_id, number_parts=1, md5_parts={"1": "ASDF"}
        )
        self.print_success(f" -- upload_id: {upload_id}")

    def list(self):
        for upload in AssetUpload.objects.filter(status=BaseAssetUpload.Status.IN_PROGRESS):
            self.print(f"> {upload.upload_id} (asset: {upload.asset.name})")

    def complete(self):
        try:
            upload = AssetUpload.objects.get(upload_id=self.options['upload_id'])
            upload.status = BaseAssetUpload.Status.COMPLETED
            upload.save()
        except AssetUpload.DoesNotExist:
            self.print_error(f"upload_id '{self.options['upload_id']}' doesn't exist")

    def abort(self):
        try:
            upload = AssetUpload.objects.get(upload_id=self.options['upload_id'])
            upload.status = BaseAssetUpload.Status.ABORTED
            upload.save()
        except AssetUpload.DoesNotExist:
            self.print_error(f"upload_id {self.options['upload_id']} doesn't exist")


class Command(CustomBaseCommand):
    help = """Start dummy Multipart upload for asset file on S3 for testing.
    """

    def add_arguments(self, parser):
        super().add_arguments(parser)

        subparsers = parser.add_subparsers(
            dest='action',
            required=True,
            help='Define the action to be performed, either "start" (default) to initate '
            ' and upload, "complete" to end it or "abort" to cancel it'
        )

        # create the parser for the "start" command
        parser_start = subparsers.add_parser('start', help='start help')
        parser_start.add_argument(
            '--asset-id',
            type=str,
            required=True,
            help="The asset-id for which data should be uploaded"
        )
        parser_start.set_defaults()

        # create the parser for the "complete" command
        parser_complete = subparsers.add_parser('complete', help='complete help')
        parser_complete.add_argument(
            '--upload-id', type=str, required=True, help="The upload-id to complete"
        )

        # create the parser for the "abort" command
        parser_abort = subparsers.add_parser('abort', help='abort help')
        parser_abort.add_argument(
            '--upload-id', type=str, required=True, help="The upload-id to abort"
        )

    def handle(self, *args, **options):
        handler = DummyAssetUploadHandler(self, options)
        if options['action'] == 'start':
            handler.start()
        elif options['action'] == 'list':
            handler.list()
        elif options['action'] == 'complete':
            handler.complete()
        elif options['action'] == 'abort':
            handler.abort()
