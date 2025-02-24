from io import BytesIO
import logging
import os
import base64
import hashlib
import time
import requests

from stac_api.s3_multipart_upload import MultipartUpload
from stac_api.models.item import Asset, AssetUpload
from stac_api.models.general import BaseAssetUpload
from stac_api.utils import get_asset_path, get_sha256_multihash, AVAILABLE_S3_BUCKETS

logger = logging.getLogger(__name__)


class TestAssetUploadHandler:
    """
    Handles the upload of an asset in a single part to S3.
    This follows the logic of the JavaScript frontend uploader.
    """

    def __init__(self):
        self.upload_id = None
        s3_bucket = AVAILABLE_S3_BUCKETS.legacy
        self.uploader = MultipartUpload(s3_bucket)

    def _compute_md5_base64(self, file_content):
        """Compute MD5 checksum and encode it in base64 (required for S3)."""
        md5_digest = hashlib.md5(file_content).digest()
        return base64.b64encode(md5_digest).decode('utf-8')

    def start(self, asset, file_content):
        """Upload a file to S3 in a single part using a presigned URL and finalize the upload."""
        logger.info(f"Starting single-part upload for {asset}")

        key = get_asset_path(asset.item, asset.name)
        logger.info(f"Uploading {asset} as {key}")

        if isinstance(file_content, BytesIO):
            file_content.seek(0)
            file_bytes = file_content.getvalue()
            file_name = getattr(file_content, "name", "default_filename.bin")
        else:
            logger.error("file_content should be a BytesIO object")
            return

        # Compute checksums
        checksum_multihash = get_sha256_multihash(file_bytes)
        logger.info(f"Checksum for asset {asset}: {checksum_multihash}")
        md5_base64 = self._compute_md5_base64(file_bytes)

        self.upload_id = self.uploader.create_multipart_upload(
            key=key,
            asset=asset,
            checksum_multihash=checksum_multihash,
            update_interval=360,
            content_encoding=None
        )

        presigned_url_data = self.uploader.create_presigned_url(
            key=key,
            asset=asset,
            part=1,  # Only one part
            upload_id=self.upload_id,
            part_md5=md5_base64
        )

        presigned_url = presigned_url_data['url']

        headers = {
            "Content-MD5": md5_base64,
            "Content-Type": "binary/octet-stream",
            "Content-Length": str(len(file_bytes))
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.put(
                    presigned_url, data=file_bytes, headers=headers, timeout=(30, 30)
                )
                if response.status_code == 200:
                    break
            except requests.exceptions.RequestException as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                time.sleep(2**attempt)  # Exponential backoff
        else:
            logger.error("Max retries reached. Upload failed.")
            self.abort(key, asset)
            return

        etag = response.headers.get('ETag')

        self.uploader.complete_multipart_upload(
            key=key, asset=asset, parts=[{
                "ETag": etag, "PartNumber": 1
            }], upload_id=self.upload_id
        )

        AssetUpload.objects.create(
            asset=asset,
            upload_id=self.upload_id,
            number_parts=1,
            md5_parts={"1": md5_base64},
            status=BaseAssetUpload.Status.COMPLETED
        )

        asset.checksum_multihash = checksum_multihash
        asset.save()

        logger.info(f"File {file_name} uploaded successfully to S3 as {key}")

    def abort(self, key, asset):
        """Abort the upload in case of failure."""
        if not self.upload_id:
            logger.error("No active upload_id found to abort.")
            return

        try:
            upload = AssetUpload.objects.get(upload_id=self.upload_id)
            self.uploader.abort_multipart_upload(key, asset, self.upload_id)
            upload.status = BaseAssetUpload.Status.ABORTED
            upload.save()
            logger.info(f"Upload {self.upload_id} aborted successfully.")
        except AssetUpload.DoesNotExist:
            logger.error(f"upload_id {self.upload_id} doesn't exist")
