from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import Keyword
from stac_api.models import Provider
from stac_api.models import get_default_stac_extensions


def create_collection():
    '''Create a dummy collection db object for testing
    '''
    collection = Collection.objects.create(
        crs=["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
        created='2020-10-28T13:05:10.473602Z',
        updated='2020-10-28T13:05:10.473602Z',
        description='This is a description',
        start_date=None,
        end_date=None,
        extent=[200000, 100000, 200001, 100005],
        collection_name='ch.swisstopo.pixelkarte-farbe-pk200.noscale',
        item_type='Feature',
        license='test',
        stac_extension=get_default_stac_extensions(),
        stac_version="0.9.0",
        summaries_eo_gsd=[10.1, 20.3, 30.44],
        summaries_proj=[1, 4, 22],
        geoadmin_variant=['blubb', 'blabb', 'blibb'],
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


def create_item(collection):
    '''Create a dummy item db object for testing
    '''
    # create item instance for testing
    item = Item.objects.create(
        collection=collection,
        item_name='item-for-test',
        properties_datetime='2020-10-28T13:05:10.473602Z',
        properties_eo_gsd=[10, 30],
        properties_title="My Title",
        stac_extensions=get_default_stac_extensions(),
        stac_version="0.9.0"
    )
    item.save()
    create_item_links(item)
    assets = create_assets(collection, item)
    item.save()
    return item, assets


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


def create_assets(collection, item):
    asset = Asset.objects.create(
        collection=collection,
        feature=item,
        title='my-title',
        asset_name="my first asset",
        checksum_multihash="01205c3fd6978a7d0b051efaa4263a09",
        description="this an asset",
        eo_gsd=3.4,
        geoadmin_lang='fr',
        geoadmin_variant="kgrs",
        proj_epsq=2056,
        media_type="image/tiff; application=geotiff; profile=cloud-optimize",
        href=
        "https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk50.noscale/smr200-200-1-2019-2056-kgrs-10.tiff"
    )
    asset.save()
    item.save()
    collection.save()
    return [asset]
