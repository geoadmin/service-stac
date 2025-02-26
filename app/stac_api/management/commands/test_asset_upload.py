from io import BytesIO
import logging
import os
import base64
import hashlib
import time
import requests

from requests.auth import HTTPBasicAuth
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

    def __init__(self, api_base_url, credentials):
        self.upload_id = None
        self.api_base_url = api_base_url
        s3_bucket = AVAILABLE_S3_BUCKETS.legacy
        self.uploader = MultipartUpload(s3_bucket)
        self.credentials = credentials

    def _compute_md5_base64(self, file_content):
        """Compute MD5 checksum and encode it in base64 (required for S3)."""
        md5_digest = hashlib.md5(file_content).digest()
        return base64.b64encode(md5_digest).decode('utf-8')

    def start(self, item, asset, file_content):
        """Upload a file to S3 in a single part using a presigned URL and finalize the upload."""
        logger.info(f"Starting single-part upload for {asset}")

        key = get_asset_path(asset.item, asset.name)
        logger.info(f"Uploading {asset} as {key}")

        try:
            file_content.seek(0)
            file_bytes = file_content.getvalue()
            file_name = getattr(file_content, "name", "default_filename.bin")
        except AttributeError:
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

        presigned_url_data = self.create_presigned(
            item.collection.name, item.name, asset.name, md5_base64, checksum_multihash
        )

        presigned_url = presigned_url_data['url']

        headers = {
            "Content-MD5": md5_base64,
            "Content-Type": "binary/octet-stream",
            "Content-Length": str(len(file_bytes))
        }

        logger.info("PUT request at url %s", presigned_url)

        response = requests.put(presigned_url, data=file_bytes, headers=headers)

        if response:
            logger.info(f"File uploaded successfully with ETag: {response.headers.get('ETag')}")
        else:
            logger.error("Upload failed after retries.")

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

    def create_presigned(self, collection_name, item_name, asset_name, md5, multihash):
        """
        Create a presigned URL for uploading an asset.

        Args:
            collection_name (str): Name of the collection.
            item_name (str): Name of the item.
            asset_name (str): Name of the asset.
            md5 (str): Base64-encoded MD5 checksum.
            multihash (str): Multihash of the file.

        Returns:
            dict: JSON response containing the presigned URL or None if failed.
        """
        url = f"{self.api_base_url}/api/stac/v1/collections/{collection_name}/items/{item_name}/assets/{asset_name}/uploads"

        collections_url = f"{self.api_base_url}/api/stac/v1/collections"

        sanity_check = requests.get(collections_url, auth=("postgres", "postgres"))
        logger.info(f"Collections available: {sanity_check.json()}")

        headers = {
            "X-CSRFToken": "some token",
            "Content-Type": "application/json; charset=utf-8",
        }

        payload = {
            "number_parts": 1,
            "md5_parts": [{
                "part_number": 1, "md5": md5
            }],
            "file:checksum": multihash,
        }

        try:
            logger.info(f"Creating presigned URL for {asset_name} at {url}")

            # Send request with Basic Authentication
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                auth=("postgres", "postgres"),
                timeout=10,
            )

            if response.status_code == 200:
                logger.info("Presigned URL created successfully.")
                return response.json()  # Return presigned URL JSON data

            logger.error(
                f"Failed to create presigned URL: {response.status_code} - {response.text}"
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"CreatePresigned failed: {e}")

        return None  # Return None if the request fails
