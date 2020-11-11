import logging
from datetime import datetime
import random

from django.core.exceptions import ValidationError
from django.test import TestCase

from stac_api.models import Item
from stac_api.models import Asset
from stac_api.utils import utc_aware

import tests.database as db

logger = logging.getLogger(__name__)


class ItemsModelTestCase(TestCase):

    def setUp(self):
        self.collection = db.create_collection('collection-1')

    def test_item_create_model(self):
        item = Item.objects.create(
            collection=self.collection,
            item_name='item-1',
            properties_datetime=utc_aware(datetime.utcnow())
        )
        item.full_clean()
        item.save()
        self.assertEqual('item-1', item.item_name)

    def test_item_create_model_invalid_datetime(self):
        with self.assertRaises(ValidationError, msg="no datetime is invalid"):
            item = Item.objects.create(collection=self.collection, item_name='item-1')
            item.clean()

        with self.assertRaises(ValidationError, msg="only start_datetime is invalid"):
            item = Item.objects.create(
                collection=self.collection,
                item_name='item-2',
                properties_start_datetime=utc_aware(datetime.utcnow())
            )
            item.clean()

        with self.assertRaises(ValidationError, msg="only end_datetime is invalid"):
            item = Item.objects.create(
                collection=self.collection,
                item_name='item-3',
                properties_end_datetime=utc_aware(datetime.utcnow())
            )
            item.clean()

        with self.assertRaises(ValidationError, msg="datetime is not allowed with start_datetime"):
            item = Item.objects.create(
                collection=self.collection,
                item_name='item-4',
                properties_datetime=utc_aware(datetime.utcnow()),
                properties_start_datetime=utc_aware(datetime.utcnow()),
                properties_end_datetime=utc_aware(datetime.utcnow())
            )
            item.clean()

        with self.assertRaises(ValidationError):
            item = Item.objects.create(
                collection=self.collection, item_name='item-1', properties_datetime='asd'
            )

        with self.assertRaises(ValidationError):
            item = Item.objects.create(
                collection=self.collection, item_name='item-4', properties_start_datetime='asd'
            )

        with self.assertRaises(ValidationError):
            item = Item.objects.create(
                collection=self.collection, item_name='item-1', properties_end_datetime='asd'
            )

    def test_item_property_eo_gsd(self):
        item = db.create_item(self.collection, 'item-1')
        item.full_clean()
        item.save()
        self.assertIsNone(item.properties_eo_gsd, msg='Initial property eo:gsd should be none')

        eo_gsd = []
        assets = []
        for i in range(random.randrange(5, 10)):
            eo_gsd.append(round(random.uniform(1, 50), 3))
            asset = Asset.objects.create(
                collection=self.collection,
                item=item,
                title='my-title',
                asset_name=f'asset-{i}',
                checksum_multihash="01205c3fd6978a7d0b051efaa4263a09",
                description="this an asset",
                eo_gsd=eo_gsd[i],
                geoadmin_lang='fr',
                geoadmin_variant="kgrs",
                proj_epsg=2056,
                media_type="image/tiff; application=geotiff; profile=cloud-optimize",
                href=
                "https://data.geo.admin.ch/ch.swisstopo.pixelkarte-farbe-pk50.noscale/smr200-200-1-2019-2056-kgrs-10.tiff"
            )
            asset.full_clean()
            asset.save()
            assets.append(asset)
        logger.debug('List of eo:gsd: %s, min %d', eo_gsd, min(eo_gsd))
        self.assertEqual(
            item.properties_eo_gsd, min(eo_gsd), msg='eo:gsd is not the min value from asset'
        )

        # remove last element
        deleted = assets[-1].delete()
        eo_gsd.pop()
        logger.debug('Deleted asset: %s', deleted)
        logger.debug('Remove last eo:gsd: %s, min %d', eo_gsd, min(eo_gsd))
        self.assertEqual(
            item.properties_eo_gsd, min(eo_gsd), msg='eo:gsd is not the min value from asset'
        )

        # remove smallest element
        i = eo_gsd.index(min(eo_gsd))
        smallest = eo_gsd.pop(i)
        asset = assets.pop(i)
        deleted = asset.delete()
        logger.debug('Deleted asset: %s', deleted)
        logger.debug('Removed smallest eo:gsd %d: %s, min %d', smallest, eo_gsd, min(eo_gsd))
        self.assertEqual(
            item.properties_eo_gsd, min(eo_gsd), msg='eo:gsd is not the min value from asset'
        )
