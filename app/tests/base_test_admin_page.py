import logging
import time
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from stac_api.models.general import Asset
from stac_api.models.general import Collection
from stac_api.models.general import CollectionLink
from stac_api.models.general import Item
from stac_api.models.general import ItemLink
from stac_api.models.general import Provider

from tests.tests_09.data_factory import Factory

logger = logging.getLogger(__name__)


class AdminBaseTestCase(TestCase):

    def setUp(self):
        self.factory = Factory()
        self.password = 'sesame'
        self.username = 'admin_user'
        self.admin_user = get_user_model().objects.create_superuser(
            self.username, 'myemail@test.com', self.password
        )
        self.client = Client()
        self.collection = None
        self.item = None

    def _setup(self, create_collection=False, create_item=False):
        if create_collection or create_item:
            self.client.login(username=self.username, password=self.password)

        if create_collection:
            self.collection = self._create_collection()[0]
        if create_item:
            self.item = self._create_item(self.collection)[0]

    def _create_collection(self, with_link=False, with_provider=False, extra=None):
        # Post data to create a new collection
        # Note: the *-*_FORMS fields are necessary management form fields
        # originating from the AdminInline and must be present
        data = {
            "name": "test_collection",
            "license": "free",
            "description": "some very important collection",
            "published": "on",
            "providers-TOTAL_FORMS": "0",
            "providers-INITIAL_FORMS": "0",
            "links-TOTAL_FORMS": "0",
            "links-INITIAL_FORMS": "0",
            "assets-TOTAL_FORMS": "0",
            "assets-INITIAL_FORMS": "0"
        }
        if with_link:
            data.update({
                "links-TOTAL_FORMS": "1",
                "links-INITIAL_FORMS": "0",
                "links-0-href": "http://www.example.com",
                "links-0-rel": "example",
                "links-0-link_type": "example",
                "links-0-title": "Example test",
            })
        if with_provider:
            data.update({
                "providers-TOTAL_FORMS": "1",
                "providers-INITIAL_FORMS": "0",
                "providers-0-name": "my-provider",
                "providers-0-description": "This is a provider",
                "providers-0-roles": "licensor",
                "providers-0-url": "http://www.example.com",
            })
        if extra is not None:
            data.update(extra)
        response = self.client.post(reverse('admin:stac_api_collection_add'), data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to add new collection")
        self.assertTrue(
            Collection.objects.filter(name=data["name"]).exists(),
            msg="Admin page collection added not found in DB"
        )
        collection = Collection.objects.get(name=data["name"])
        link = None
        provider = None

        if with_link:
            self.assertTrue(
                CollectionLink.objects.filter(collection=collection,
                                              rel=data["links-0-rel"]).exists(),
                msg="Admin page Link added not found in DB"
            )
            link = CollectionLink.objects.get(collection=collection, rel=data["links-0-rel"])

        if with_provider:
            self.assertTrue(
                Provider.objects.filter(collection=collection,
                                        name=data["providers-0-name"]).exists(),
                msg="Admin page Provider added not found in DB"
            )
            provider = Provider.objects.get(collection=collection, name=data["providers-0-name"])

        return collection, data, link, provider

    def _create_item(self, collection, with_link=False, extra=None, data=None):

        # Post data to create a new item
        # Note: the *-*_FORMS fields are necessary management form fields
        # originating from the AdminInline and must be present
        if not data:
            data = {
                "collection": collection.id,
                "name": "test_item",
                "geometry":
                    "SRID=4326;POLYGON((5.96 45.82, 5.96 47.81, 10.49 47.81, 10.49 45.82, "\
                        "5.96 45.82))",
                "text_geometry":
                    "SRID=4326;POLYGON((5.96 45.82, 5.96 47.81, 10.49 47.81, 10.49 45.82, "\
                        "5.96 45.82))",
                "properties_datetime_0": "2020-12-01",
                "properties_datetime_1": "13:15:39",
                "properties_title": "test",
                "links-TOTAL_FORMS": "0",
                "links-INITIAL_FORMS": "0",
            }
        if with_link:
            data.update({
                "links-TOTAL_FORMS": "1",
                "links-INITIAL_FORMS": "0",
                "links-0-href": "http://www.example.com",
                "links-0-rel": "example",
                "links-0-link_type": "example",
                "links-0-title": "Example test",
            })
        if extra:
            data.update(extra)
        response = self.client.post(reverse('admin:stac_api_item_add'), data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to add new item")
        self.assertTrue(
            Item.objects.filter(collection=collection, name=data["name"]).exists(),
            msg="Admin page item added not found in DB"
        )
        item = Item.objects.get(collection=collection, name=data["name"])
        link = None

        if with_link:
            self.assertTrue(
                ItemLink.objects.filter(item=item, rel=data["links-0-rel"]).exists(),
                msg="Admin page Link added not found in DB"
            )
            link = ItemLink.objects.get(item=item, rel=data["links-0-rel"])

        # Check the item values
        for key, value in data.items():
            if key in [
                'collection',
                'id',
                'properties_datetime_0',
                'properties_datetime_1',
                'text_geometry'
            ]:
                continue
            if key.startswith('links-0-'):
                self.assertEqual(
                    getattr(link, key[8:]), value, msg=f"Item link field {key} value missmatch"
                )
            elif key.startswith('links-'):
                continue
            else:
                self.assertEqual(getattr(item, key), value, msg=f"Item field {key} value missmatch")

        return item, data, link

    def _create_asset_minimal(self, item):
        start = time.time()
        filecontent = b'my binary data'
        filelike = BytesIO(filecontent)
        filelike.name = 'testname.txt'

        # we need to create the asset in two steps, since the django admin form
        # only takes some values in the creation form, then the rest in the
        # change form
        data = {
            "item": item.id,
            "name": "test_asset.txt",
            "media_type": "text/plain",
        }

        response = self.client.post(reverse('admin:stac_api_asset_add'), data)
        logger.debug('Asset created in %fs', time.time() - start)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to add new asset")
        self.assertTrue(
            Asset.objects.filter(item=item, name=data["name"]).exists(),
            msg="Admin page asset added not found in DB"
        )

        data = {
            "item": item.id,
            "name": "test_asset.txt",
            "description": "",
            "eo_gsd": "",
            "geoadmin_lang": "",
            "geoadmin_variant": "",
            "proj_epsg": "",
            "title": "",
            "media_type": "text/plain",
            "file": filelike
        }

        asset = Asset.objects.get(item=item, name=data["name"])
        response = self.client.post(reverse('admin:stac_api_asset_change', args=[asset.id]), data)

        asset.refresh_from_db()

        # Check the asset values
        for key, value in data.items():
            if key in ['item', 'name', 'file', 'checksum_multihash']:
                continue
            self.assertEqual(
                getattr(asset, key),
                value if value else None,
                msg=f"Asset field {key} value missmatch"
            )

        # Assert that the filename is set to the value in name
        self.assertEqual(asset.filename, data['name'])

        # Check file content is correct
        with asset.file.open() as fd:
            self.assertEqual(filecontent, fd.read())

        return asset, data

    def _create_asset(self, item, extra=None):
        start = time.time()
        filecontent = b'mybinarydata'
        filelike = BytesIO(filecontent)
        filelike.name = 'testname.zip'

        data = {
            "item": item.id,
            "name": filelike.name,
            "media_type": "application/x.filegdb+zip",
        }
        if extra:
            data.update(extra)
        response = self.client.post(reverse('admin:stac_api_asset_add'), data)
        logger.debug('Asset created in %fs', time.time() - start)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to add new asset")
        self.assertTrue(
            Asset.objects.filter(item=item, name=data["name"]).exists(),
            msg="Admin page asset added not found in DB"
        )

        data = {
            "item": item.id,
            "name": filelike.name,
            "description": "This is a description",
            "eo_gsd": 10,
            "geoadmin_lang": "en",
            "geoadmin_variant": "kgrs",
            "proj_epsg": 2056,
            "title": "My first Asset for test",
            "media_type": "application/x.filegdb+zip",
            "file": filelike
        }

        asset = Asset.objects.get(item=item, name=data["name"])
        response = self.client.post(reverse('admin:stac_api_asset_change', args=[asset.id]), data)

        asset.refresh_from_db()

        # Check the asset values
        for key, value in data.items():
            if key in ['item', 'id', 'file']:
                continue
            self.assertEqual(getattr(asset, key), value, msg=f"Asset field {key} value missmatch")

        # Assert that the filename is set to the value in name
        self.assertEqual(asset.filename, data['name'])

        # Check file content is correct
        with asset.file.open() as fd:
            self.assertEqual(filecontent, fd.read())

        return asset, data
