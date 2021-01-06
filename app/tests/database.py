import hashlib
import json

import boto3
import botocore
import multihash
from dateutil.parser import isoparse
from moto import mock_s3

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import Provider

ASSET_FILE_DUMMY_CONTENT = '{asset_name}: Asset file dummy content'


def get_asset_dummy_content(asset_name):
    '''Get an asset file dummy content based on its name

    Args:
        asset_name: string

    Returns:
        Asset personalized in bytes
    '''
    return ASSET_FILE_DUMMY_CONTENT.format(asset_name=asset_name).encode('utf-8')


def get_asset_dummy_content_multihash(asset_name):
    '''Returns the multihash (sha2-256) of an Asset personalized dummy content

    Args:
        asset_name: string

    Returns:
        multihash string
    '''
    digest = hashlib.sha256(get_asset_dummy_content(asset_name)).digest()
    return multihash.to_hex_string(multihash.encode(digest, 'sha2-256'))


def create_collection(name):
    '''Create a dummy collection db object for testing
    '''
    collection = Collection.objects.create(
        created=isoparse('2020-10-28T13:05:10Z'),
        updated=isoparse('2020-10-28T13:05:10Z'),
        description='This is a description',
        name=name,
        license='test',
        summaries={
            "eo:gsd": [], "geoadmin:variant": [], "proj:epsg": []
        },
        title='Test title'
    )
    collection.full_clean()
    collection.save()

    # create provider instance for testing
    provider = Provider.objects.create(
        collection=collection,
        name='provider1',
        description='description',
        roles=['licensor'],
        url='http://www.google.com'
    )
    provider.full_clean()
    provider.save()
    collection.providers.add(provider)

    # Create a dummy link
    link = CollectionLink.objects.create(
        collection=collection,
        href='http://www.google.com',
        rel='dummy',
        link_type='dummy',
        title='Dummy link'
    )
    link.full_clean()
    link.save()
    collection.save()
    provider.save()

    return collection


def create_item(collection, name):
    '''Create a dummy item db object for testing
    '''
    # create item instance for testing
    # yapf: disable
    item = Item.objects.create(
        collection=collection,
        name=name,
        properties_datetime=isoparse('2020-10-28T13:05:10Z'),
        properties_title="My Title",
        geometry=GEOSGeometry(
            json.dumps({
                "coordinates": [[
                        [5.644711, 46.775054],
                        [5.644711, 48.014995],
                        [6.602408, 48.014995],
                        [7.602408, 49.014995],
                        [5.644711, 46.775054]
                ]],
                "type": "Polygon",
            })
        )
    )
    # yapf: enable
    item.full_clean()
    item.save()
    create_item_links(item)
    item.save()
    collection.save()
    return item


def create_item_links(item):
    # create links instances for testing
    link = ItemLink.objects.create(
        item=item,
        href="https://example.com",
        rel='dummy',
        link_type='dummy',
        title='Dummy link',
    )
    link.full_clean()
    link.save()
    item.save()
    return [link]


@override_settings(
    AWS_ACCESS_KEY_ID='mykey',
    AWS_DEFAULT_ACL='public-read',
    AWS_S3_REGION_NAME='wonderland',
    AWS_S3_ENDPOINT_URL=None
)
def create_asset(item, name, eo_gsd=3.4, geoadmin_variant="kgrs", proj_epsg=2056, bucket=None):
    mock = None
    if bucket is None:
        mock = mock_s3()
        mock.start()
        # Check if the bucket exists and if not, create it
        s3 = boto3.resource('s3', region_name='wonderland')
        try:
            s3.meta.client.head_bucket(Bucket=settings.AWS_STORAGE_BUCKET_NAME)
        except botocore.exceptions.ClientError as e:  # pylint: disable=invalid-name
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # We need to create the bucket since this is all in Moto's 'virtual' AWS account
                s3.create_bucket(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    CreateBucketConfiguration={'LocationConstraint': 'wonderland'}
                )
        else:
            raise NotImplementedError()

    asset = Asset(
        item=item,
        title='my-title',
        name=name,
        description="this an asset",
        eo_gsd=eo_gsd,
        geoadmin_lang='fr',
        geoadmin_variant=geoadmin_variant,
        proj_epsg=proj_epsg,
        media_type="image/tiff; application=geotiff; profile=cloud-optimized",
        file=SimpleUploadedFile('some_name.tiff', get_asset_dummy_content(name))
    )
    asset.full_clean()
    asset.save()
    item.save()

    if mock is not None:
        mock.stop()

    return asset


def create_dummy_db_content(nb_collections, nb_items=0, nb_assets=0, bucket=None):
    collections = []
    items = []
    assets = []
    for i in range(nb_collections):
        collection = create_collection(f'collection-{i+1}')
        collections.append(collection)
        items.append([])
        assets.append([])
        for j in range(nb_items):
            item = create_item(collection, f'item-{i+1}-{j+1}')
            items[i].append(item)
            assets[i].append([])
            for k in range(nb_assets):
                asset = create_asset(item, f'asset-{i+1}-{j+1}-{k+1}', bucket=bucket)
                assets[i][j].append(asset)

    return collections, items, assets
