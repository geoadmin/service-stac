import logging
from datetime import datetime
from json import dumps
from json import loads
from pprint import pformat
from urllib.parse import urlparse

import boto3
import botocore
import requests_mock
from moto import mock_s3

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.test import override_settings

from rest_framework.test import APIRequestFactory

from stac_api.models import Asset
from stac_api.serializers import AssetSerializer
from stac_api.utils import fromisoformat
from stac_api.utils import utc_aware

import tests.database as db
from tests.base_test import StacBaseTestCase
from tests.utils import get_http_error_description

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


def to_dict(input_ordered_dict):
    return loads(dumps(input_ordered_dict))


class AssetsEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.factory = APIRequestFactory()
        self.client = Client()
        self.collections, self.items, self.assets = db.create_dummy_db_content(4, 4, 2)
        self.maxDiff = None  # pylint: disable=invalid-name
        self.username = 'SherlockHolmes'
        self.password = '221B_BakerStreet'
        self.superuser = get_user_model().objects.create_superuser(
            self.username, 'test_e_mail1234@some_fantasy_domainname.com', self.password
        )

    def test_assets_endpoint(self):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        response = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_name}/assets"
        )
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        # Check that the answer is equal to the initial data
        serializer = AssetSerializer(
            self.assets[0][0], many=True, context={'request': response.wsgi_request}
        )
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            original_data, json_data, msg="Returned data does not match expected data"
        )

    def test_single_asset_endpoint(self):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_name = self.assets[0][0][0].name
        response = self.client.get(
            f"/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}"
        )
        json_data = response.json()
        self.assertEqual(200, response.status_code, msg=get_http_error_description(json_data))
        logger.debug('Response (%s):\n%s', type(json_data), pformat(json_data))

        # The ETag change between each test call due to the created, updated time that are in the
        # hash computation of the ETag
        self.check_etag(None, response)

        # Check that the answer is equal to the initial data
        serializer = AssetSerializer(
            self.assets[0][0][0], context={'request': response.wsgi_request}
        )
        original_data = to_dict(serializer.data)
        logger.debug('Serialized data:\n%s', pformat(original_data))
        self.assertDictEqual(
            original_data, json_data, msg="Returned data does not match expected data"
        )
        # created and updated must exist and be a valid date
        date_fields = ['created', 'updated']
        for date_field in date_fields:
            self.assertTrue(
                fromisoformat(json_data[date_field]),
                msg=f"The field {date_field} has an invalid date"
            )


@requests_mock.Mocker(kw='mock')
@override_settings(
    AWS_ACCESS_KEY_ID='mykey',
    AWS_DEFAULT_ACL='public-read',
    AWS_S3_REGION_NAME='wonderland',
    AWS_S3_ENDPOINT_URL=None
)
@mock_s3
class AssetsWriteEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.factory = APIRequestFactory()
        self.client = Client()
        bucket = self._create_s3_bucket()
        self.collections, self.items, self.assets = db.create_dummy_db_content(
            4, 4, 2, bucket=bucket
        )
        self.maxDiff = None  # pylint: disable=invalid-name
        self.username = 'SherlockHolmes'
        self.password = '221B_BakerStreet'
        self.superuser = get_user_model().objects.create_superuser(
            self.username, 'test_e_mail1234@some_fantasy_domainname.com', self.password
        )

    def _create_s3_bucket(self):
        # We need to create the bucket since this is all in Moto's 'virtual' AWS account
        s3 = boto3.resource('s3', region_name=settings.AWS_S3_REGION_NAME)
        bucket_exists = False
        try:
            s3.meta.client.head_bucket(Bucket=settings.AWS_STORAGE_BUCKET_NAME)
        except botocore.exceptions.ClientError as error:
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            if error.response['Error']['Code'] != '404':
                raise NotImplementedError()
        else:
            bucket_exists = True

        if not bucket_exists:
            # We need to create the bucket since this is all in Moto's 'virtual' AWS account
            s3.create_bucket(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                CreateBucketConfiguration={'LocationConstraint': settings.AWS_S3_REGION_NAME}
            )
        return True

    def test_asset_endpoint_post_only_required(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_id = "test123"
        data = {
            "id": asset_id,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "checksum:multihash":
                "1220b0c2185619a5a9be2d27cfaf51bc3a6a18b2b0727b7e58760cfe6b2a36193c30",
        }
        # mock the requests.head() to the assets on S3 for asset validation
        mock.head(
            f'http://{settings.AWS_S3_CUSTOM_DOMAIN}/{collection_name}/{item_name}/{asset_id}',
            headers={'x-amz-meta-sha256': data['checksum:multihash'][4:]}
        )
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        self.client.login(username=self.username, password=self.password)
        response = self.client.post(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.assertTrue(response.has_header('Location'), msg="Location header is missing")
        self.assertEqual(
            urlparse(response['Location']).path, f'{path}/{data["id"]}', msg="Wrong location path"
        )
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

    def test_asset_endpoint_post_full(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_id = "test123"
        data = {
            "id": asset_id,
            "title": "test-title1",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "description": "test description number 1",
            "eo:gsd": 10,
            "proj:epsg": 2056,
            "geoadmin:variant": "krel",
            "geoadmin:lang": "it",
            "href":
                f'http://{settings.AWS_S3_CUSTOM_DOMAIN}/{collection_name}/{item_name}/{asset_id}',
            "checksum:multihash":
                "1220b0c2185619a5a9be2d27cfaf51bc3a6a18b2b0727b7e58760cfe6b2a36193c30",
        }
        # mock the requests.head() to the assets on S3 for asset validation
        mock.head(
            f'http://{settings.AWS_S3_CUSTOM_DOMAIN}/{collection_name}/{item_name}/{asset_id}',
            headers={'x-amz-meta-sha256': data['checksum:multihash'][4:]}
        )
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        self.client.login(username=self.username, password=self.password)
        response = self.client.post(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(201, response)
        self.assertTrue(response.has_header('Location'), msg="Location header is missing")
        self.assertEqual(
            urlparse(response['Location']).path, f'{path}/{data["id"]}', msg="Wrong location path"
        )
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(response['Location'])
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_item(data, json_data)

    def test_asset_endpoint_post_extra_payload(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_id = "test123"
        data = {
            "id": asset_id,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "checksum:multihash": "4473e458e35568687564de38ed134d0b",
            "crazy:stuff": "woooohoooo"
        }
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        self.client.login(username=self.username, password=self.password)
        response = self.client.post(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_asset_endpoint_post_read_only_in_payload(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_id = "test123"
        data = {
            "id": asset_id,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "checksum:multihash": "4473e458e35568687564de38ed134d0b",
            "created": utc_aware(datetime.utcnow())
        }
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        self.client.login(username=self.username, password=self.password)
        response = self.client.post(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_asset_endpoint_post_invalid_data(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_id = "test123+invalid name"
        data = {
            "id": asset_id,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "checksum:multihash": "4473e458e35568687564de38ed134d0b",
        }
        # mock the requests.head() to the assets on S3 for asset validation
        mock.head(
            f'http://{settings.AWS_S3_CUSTOM_DOMAIN}/{collection_name}/{item_name}/{asset_id}',
            headers={'x-amz-meta-sha256': data['checksum:multihash'][4:]}
        )
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        self.client.login(username=self.username, password=self.password)
        response = self.client.post(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

        # Make sure that the asset is not found in DB
        self.assertFalse(
            Asset.objects.filter(name=data['id']).exists(),
            msg="Invalid item has been created in DB"
        )

    def test_asset_endpoint_put(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_name = self.assets[0][0][0].name
        data = {
            "id": asset_name,
            "title": "my-title",
            "checksum:multihash":
                "1220b0c2185619a5a9be2d27cfaf51bc3a6a18b2b0727b7e58760cfe6b2a36193c30",
            "description": "this an asset",
            "eo:gsd": 10,
            "geoadmin:lang": "fr",
            "geoadmin:variant": "krel",
            "proj:epsg": 2056,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        }
        # mock the requests.head() to the assets on S3 for asset validation
        mock.head(
            f'http://{settings.AWS_S3_CUSTOM_DOMAIN}/{collection_name}/{item_name}/{asset_name}',
            headers={'x-amz-meta-sha256': data['checksum:multihash'][4:]}
        )
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(data, json_data)

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(data, json_data)

    def test_asset_endpoint_put_extra_payload(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_name = self.assets[0][0][0].name
        data = {
            "id": asset_name,
            "title": "my-title",
            "checksum:multihash": "01205c3fd6978a7d0b051efaa4263a09",
            "description": "this an asset",
            "eo:gsd": 10,
            "geoadmin:lang": "fr",
            "geoadmin:variant": "krel",
            "proj:epsg": 2056,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "crazy:stuff": "woooohoooo"
        }
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_asset_endpoint_put_read_only_in_payload(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_name = self.assets[0][0][0].name
        data = {
            "id": asset_name,
            "title": "my-title",
            "checksum:multihash": "01205c3fd6978a7d0b051efaa4263a09",
            "description": "this an asset",
            "eo:gsd": 10,
            "geoadmin:lang": "fr",
            "geoadmin:variant": "krel",
            "proj:epsg": 2056,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "created": utc_aware(datetime.utcnow())
        }
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(path, data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_asset_endpoint_put_change_title(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_name = self.assets[0][0][0].name
        new_title = "new-title123abc"
        data = {
            "id": asset_name,
            "title": new_title,
            "checksum:multihash":
                "1220b0c2185619a5a9be2d27cfaf51bc3a6a18b2b0727b7e58760cfe6b2a36193c30",
            "description": "this an asset",
            "eo:gsd": 10,
            "geoadmin:lang": "fr",
            "geoadmin:variant": "krel",
            "proj:epsg": 2056,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        }
        # mock the requests.head() to the assets on S3 for asset validation
        mock.head(
            f'http://{settings.AWS_S3_CUSTOM_DOMAIN}/{collection_name}/{item_name}/{asset_name}',
            headers={'x-amz-meta-sha256': data['checksum:multihash'][4:]}
        )
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(new_title, json_data['title'], msg="Title has not been updated correctly")
        self.check_stac_asset(data, json_data)

        # Check the data by reading it back
        response = self.client.get(path)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.check_stac_asset(data, json_data)

    def test_asset_endpoint_put_rename_asset(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_name = self.assets[0][0][0].name
        new_asset_name = "new-name-123abc"
        data = {
            "id": new_asset_name,
            "checksum:multihash":
                "1220b0c2185619a5a9be2d27cfaf51bc3a6a18b2b0727b7e58760cfe6b2a36193c30",
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        }
        # mock the requests.head() to the assets on S3 for asset validation
        mock.head(
            f'http://{settings.AWS_S3_CUSTOM_DOMAIN}/{collection_name}/{item_name}/{new_asset_name}',
            headers={'x-amz-meta-sha256': data['checksum:multihash'][4:]}
        )
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(path, data=data, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(data['id'], json_data['id'])
        self.check_stac_item(data, json_data)

    def test_asset_endpoint_patch_rename_asset(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_name = self.assets[0][0][0].name
        new_asset_name = "new-name-123abc"
        data = {
            "id": new_asset_name,
        }
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.patch(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(data['id'], json_data['id'])
        self.check_stac_item(data, json_data)

        # Check the data by reading it back
        response = self.client.get(
            f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{new_asset_name}'
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(data['id'], json_data['id'])
        self.check_stac_item(data, json_data)

    def test_asset_endpoint_patch_extra_payload(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_name = self.assets[0][0][0].name
        new_asset_name = "new-name-123abc"
        data = {"id": new_asset_name, "crazy:stuff": "woooohoooo"}
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.patch(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(400, response)

    def test_asset_endpoint_patch_read_only_in_payload(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_name = self.assets[0][0][0].name
        new_asset_name = "new-name-123abc"
        data = {"id": new_asset_name, "created": utc_aware(datetime.utcnow())}
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.patch(path, data=data, content_type="application/json")
        json_data = response.json()
        self.assertStatusCode(400, response)

    def test_asset_endpoint_delete_asset(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_name = self.assets[0][0][0].name
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.delete(path)
        self.assertStatusCode(200, response)

        # Check that is has really been deleted
        response = self.client.get(path)
        self.assertStatusCode(404, response)

        # Check that it is really not to be found in DB
        self.assertFalse(
            Asset.objects.filter(name=self.assets[0][0][0].name).exists(),
            msg="Deleted asset still found in DB"
        )

    def test_asset_endpoint_delete_asset_invalid_name(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        path = (
            f"/{API_BASE}/collections/{collection_name}"
            f"/items/{item_name}/assets/non-existent-asset"
        )
        self.client.login(username=self.username, password=self.password)
        response = self.client.delete(path)
        self.assertStatusCode(404, response)

    def test_unauthorized_asset_post_put_patch_delete(self, mock):
        collection_name = self.collections[0].name
        item_name = self.items[0][0].name
        asset_name = self.assets[0][0][0].name

        # make sure POST fails for anonymous user:
        data = {
            "id": asset_name,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "checksum:multihash":
                "1220b0c2185619a5a9be2d27cfaf51bc3a6a18b2b0727b7e58760cfe6b2a36193c30",
        }
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets'
        response = self.client.post(path, data=data, content_type="application/json")
        self.assertEqual(401, response.status_code, msg="Unauthorized post was permitted.")

        # make sure PUT fails for anonymous user:
        data = {
            "id": asset_name,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "checksum:multihash":
                "1220b0c2185619a5a9be2d27cfaf51bc3a6a18b2b0727b7e58760cfe6b2a36193c30",
        }
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.put(path, data=data, content_type="application/json")
        self.assertEqual(401, response.status_code, msg="Unauthorized put was permitted.")

        # make sure PATCH fails for anonymous user:
        data = {
            "id": asset_name,
            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
            "checksum:multihash":
                "1220b0c2185619a5a9be2d27cfaf51bc3a6a18b2b0727b7e58760cfe6b2a36193c30",
        }
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.patch(path, data=data, content_type="application/json")
        self.assertEqual(401, response.status_code, msg="Unauthorized patch was permitted.")

        # make sure DELETE fails for anonymous user:
        path = f'/{API_BASE}/collections/{collection_name}/items/{item_name}/assets/{asset_name}'
        response = self.client.delete(path)
        self.assertEqual(401, response.status_code, msg="Unauthorized delete was permitted.")
