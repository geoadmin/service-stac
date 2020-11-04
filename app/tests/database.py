from dateutil.parser import isoparse

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import Keyword
from stac_api.models import Provider


def create_collection(name):
    '''Create a dummy collection db object for testing
    '''
    collection = Collection.objects.create(
        created=isoparse('2020-10-28T13:05:10Z'),
        updated=isoparse('2020-10-28T13:05:10Z'),
        description='This is a description',
        collection_name=name,
        license='test',
        summaries={
            "eo:gsd": [], "geoadmin:variant": [], "proj:epsg": []
        },
        title='Test title'
    )
    collection.save()

    # create keyword instance for testing
    keyword1 = Keyword.objects.create(name='test1')
    keyword1.save()
    collection.keywords.add(keyword1)
    keyword2 = Keyword.objects.create(name='test2')
    keyword2.save()
    collection.keywords.add(keyword2)

    # create provider instance for testing
    provider = Provider.objects.create(
        name='provider1',
        description='description',
        roles=['licensor'],
        url='http://www.google.com'
    )
    provider.save()
    collection.providers.add(provider)

    # Create link
    link = CollectionLink.objects.create(
        collection=collection,
        href='http://www.google.com',
        rel='rel',
        link_type='root',
        title='Test title'
    )
    link.save()
    collection.save()
    keyword1.save()
    keyword2.save()
    provider.save()

    return collection


def create_item(collection, name):
    '''Create a dummy item db object for testing
    '''
    # create item instance for testing
    item = Item.objects.create(
        collection=collection,
        item_name=name,
        properties_datetime=isoparse('2020-10-28T13:05:10Z'),
        properties_eo_gsd=None,
        properties_title="My Title",
    )
    item.save()
    create_item_links(item)
    item.save()
    collection.save()
    return item


def create_item_links(item):
    # create links instances for testing
    link_root = ItemLink.objects.create(
        item=item,
        href="https://data.geo.admin.ch/api/stac/v0.9/",
        rel='root',
        link_type='root',
        title='Root link'
    )
    link_self = ItemLink.objects.create(
        item=item,
        href=
        "https://data.geo.admin.ch/collections/ch.swisstopo.pixelkarte-farbe-pk50.noscale/items/smr50-263-2016",
        rel='self',
        link_type='self',
        title='Self link'
    )
    link_rel = ItemLink.objects.create(
        item=item,
        href=
        "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.pixelkarte-farbe-pk50.noscale",
        rel='rel',
        link_type='rel',
        title='Rel link'
    )
    link_root.save()
    link_self.save()
    link_rel.save()
    item.save()
    return [link_root, link_self, link_rel]


def create_asset(collection, item, asset_name):
    asset = Asset.objects.create(
        collection=collection,
        item=item,
        title='my-title',
        asset_name=asset_name,
        checksum_multihash="01205c3fd6978a7d0b051efaa4263a09",
        description="this an asset",
        eo_gsd=3.4,
        geoadmin_lang='fr',
        geoadmin_variant="kgrs",
        proj_epsg=2056,
        media_type="image/tiff; application=geotiff; profile=cloud-optimize",
        href=
        "https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk50.noscale/smr200-200-1-2019-2056-kgrs-10.tiff"
    )
    asset.save()
    item.save()
    collection.save()
    return asset


def create_dummy_db_content(nb_collections, nb_items, nb_assets):
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
                asset = create_asset(collection, item, f'asset-{i+1}-{j+1}-{k+1}')
                assets[i][j].append(asset)

    return collections, items, assets
