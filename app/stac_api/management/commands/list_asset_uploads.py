import json

from django.core.serializers.json import DjangoJSONEncoder

from stac_api.models.item import AssetUpload
from stac_api.s3_multipart_upload import MultipartUpload
from stac_api.serializers.upload import AssetUploadSerializer
from stac_api.utils import CommandHandler
from stac_api.utils import CustomBaseCommand
from stac_api.utils import get_asset_path


class ListAssetUploadsHandler(CommandHandler):

    def __init__(self, command, options):
        super().__init__(command, options)
        self.s3 = MultipartUpload()

    def list_asset_uploads(self):
        # pylint: disable=too-many-locals
        uploads = []
        only_s3_uploads = []
        only_db_uploads = []
        s3_has_next = False
        db_has_next = False
        limit = self.options['limit']
        start = self.options['start']
        s3_key_start = self.options['s3_key_start']
        s3_upload_id_start = self.options['s3_upload_id_start']
        db_uploads_qs = None
        s3_next_key = None
        s3_next_upload_id = None

        s3_uploads = []
        if not self.options['db_only']:
            # get all s3 multipart uploads
            (
                s3_uploads,
                s3_has_next,
                s3_next_key,
                s3_next_upload_id,
            ) = self.s3.list_multipart_uploads(
                limit=limit, key=s3_key_start, start=s3_upload_id_start
            )

        if not self.options['s3_only']:
            queryset = AssetUpload.objects.filter_by_status(self.options['status'])
            count = queryset.count()
            if count > limit:
                queryset = queryset[start:start + limit]
            db_uploads_qs = queryset
            if start + limit < count:
                db_has_next = True

        if not self.options['db_only'] and not self.options['s3_only']:

            def are_uploads_equal(s3_upload, db_upload):
                if (
                    s3_upload['UploadId'] == db_upload.upload_id and
                    s3_upload['Key'] == get_asset_path(db_upload.asset.item, db_upload.asset.name)
                ):
                    return True
                return False

            # Add all db uploads
            for db_upload in db_uploads_qs:
                s3_upload = next(
                    (
                        s3_upload for s3_upload in s3_uploads
                        if are_uploads_equal(s3_upload, db_upload)
                    ),
                    None,
                )

                if s3_upload is None:
                    only_db_uploads.append(AssetUploadSerializer(instance=db_upload).data)
                else:
                    uploads.append({
                        'db': AssetUploadSerializer(instance=db_upload).data, 's3': s3_upload
                    })

            # Add s3 uploads that are not found in db uploads
            for s3_upload in s3_uploads:
                db_upload = next(
                    (
                        db_upload for db_upload in db_uploads_qs
                        if are_uploads_equal(s3_upload, db_upload)
                    ),
                    None,
                )
                if db_upload is None:
                    only_s3_uploads.append(s3_upload)
        elif self.options['db_only']:
            only_db_uploads = AssetUploadSerializer(instance=list(db_uploads_qs), many=True).data
        elif self.options['s3_only']:
            only_s3_uploads = s3_uploads

        self.print(
            json.dumps(
                {
                    'uploads': uploads,
                    'db_uploads': only_db_uploads,
                    's3_uploads': only_s3_uploads,
                    'next':
                        ' '.join([
                            f'./{self.command.prog}',
                            f'--limit={limit}',
                            f'--start={start}' if db_has_next else '',
                            f'--s3-key-start={s3_next_key}' if s3_has_next else '',
                            f'--s3-upload-id-start={s3_next_upload_id}' if s3_has_next else ''
                        ])
                },
                indent=2,
                cls=DjangoJSONEncoder,
            )
        )


class Command(CustomBaseCommand):
    help = """List all asset uploads object (DB and/or S3)

    This checks for all asset uploads object in DB (by default only returning the `in-progress`
    status objects) as well as the open S3 multipart uploads (S3 has only `in-progress` uploads,
    once the upload is completed it is automatically deleted). This command is in addition to the
    .../assets/<asset_name>/uploads which only list the uploads of one asset, while the command list
    all uploads for all assets.

    WARNINGS:
      - Although pagination is implemented, if there is more uploads than the limit, the sync
        algorithm will not work because it only search for common upload on the page context and
        uploads are not sorted.
      - The S3 minio server for local development doesn't supports the list_multipart_uploads
        methods, therefore the output will only contains the DB entries.
    """

    def add_arguments(self, parser):
        self.prog = parser.prog  # pylint: disable=attribute-defined-outside-init
        super().add_arguments(parser)

        parser.add_argument(
            '--status',
            type=str,
            default=AssetUpload.Status.IN_PROGRESS,
            help=f"Filter by status (default '{AssetUpload.Status.IN_PROGRESS}')"
        )

        default_limit = 50
        parser.add_argument(
            '--limit',
            type=int,
            default=default_limit,
            help=f"Limit the output (default {default_limit})"
        )

        parser.add_argument(
            '--start', type=int, default=0, help="Start the list at the given index (default 0)"
        )

        parser.add_argument('--db-only', type=bool, default=False, help="List only DB objects")

        parser.add_argument('--s3-only', type=bool, default=False, help="List only S3 objects")

        parser.add_argument(
            '--s3-key-start', type=str, default=None, help='Next S3 key for pagination'
        )
        parser.add_argument(
            '--s3-upload-id-start', type=str, default=None, help='Next S3 upload ID for pagination'
        )

    def handle(self, *args, **options):
        ListAssetUploadsHandler(self, options).list_asset_uploads()
