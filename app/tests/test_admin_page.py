import logging

from django.contrib.auth import get_user_model
from django.test import Client
from django.test import TestCase

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import Provider

logger = logging.getLogger(__name__)

#--------------------------------------------------------------------------------------------------


class AdminBaseTestCase(TestCase):

    def setUp(self):
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
            "providers-TOTAL_FORMS": "0",
            "providers-INITIAL_FORMS": "0",
            "links-TOTAL_FORMS": "0",
            "links-INITIAL_FORMS": "0"
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
        response = self.client.post("/api/stac/admin/stac_api/collection/add/", data)

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

    def _create_item(self, collection, with_link=False, extra=None):

        # Post data to create a new item
        # Note: the *-*_FORMS fields are necessary management form fields
        # originating from the AdminInline and must be present
        data = {
            "collection": collection.id,
            "name": "test_item",
            "geometry":
                "SRID=4326;POLYGON((5.96 45.82, 5.96 47.81, 10.49 47.81, 10.49 45.82, 5.96 45.82))",
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
        response = self.client.post("/api/stac/admin/stac_api/item/add/", data)

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
            if key in ['collection', 'id', 'properties_datetime_0', 'properties_datetime_1']:
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

    def _create_asset(self, item, extra=None):

        data = {
            "item": item.id,
            "name": "test_asset",
            "checksum_multihash": "01205c3fd6978a7d0b051efaa4263a09",
            "description": "This is a description",
            "eo_gsd": 10,
            "geoadmin_lang": "en",
            "geoadmin_variant": "kgrs",
            "proj_epsg": 2056,
            "title": "My first Asset for test",
            "media_type": "application/x.filegdb+zip",
            "href": "http://www.example.com"
        }
        response = self.client.post("/api/stac/admin/stac_api/asset/add/", data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to add new asset")
        self.assertTrue(
            Asset.objects.filter(item=item, name=data["name"]).exists(),
            msg="Admin page asset added not found in DB"
        )
        asset = Asset.objects.get(item=item, name=data["name"])

        # Check the asset values
        for key, value in data.items():
            if key in ['item', 'id']:
                continue
            self.assertEqual(getattr(asset, key), value, msg=f"Asset field {key} value missmatch")

        return asset, data


#--------------------------------------------------------------------------------------------------


class AdminTestCase(AdminBaseTestCase):

    def test_admin_page(self):
        # very simple test to check if the admin page login is up
        response = self.client.get("/api/stac/admin/login/?next=/api/stac/admin")
        self.assertEqual(response.status_code, 200, "Admin page login not up.")

    def test_login(self):
        # Make sure login of the test user works
        self.client.login(username=self.username, password=self.password)
        response = self.client.get("/api/stac/admin")
        self.assertEqual(response.status_code, 301, msg="Admin page login failed")


#--------------------------------------------------------------------------------------------------


class AdminCollectionTestCase(AdminBaseTestCase):

    def test_add_update_collection(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        collection, data = self._create_collection()[:2]

        # update some data
        data['title'] = "New title"
        response = self.client.post(
            f"/api/stac/admin/stac_api/collection/{collection.id}/change/", data
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update collection")
        collection.refresh_from_db()
        self.assertEqual(
            collection.title, data['title'], msg="Admin page collection title update did not work"
        )

    def test_add_update_collection_with_provider(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        collection, data, link, provider = self._create_collection(with_provider=True)

        # update some data in provider
        data["providers-INITIAL_FORMS"] = 1
        data["providers-0-id"] = provider.id
        data["providers-0-collection"] = collection.id
        data["providers-0-roles"] = "licensor,producer"
        response = self.client.post(
            f"/api/stac/admin/stac_api/collection/{collection.id}/change/", data
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update provider")

        provider.refresh_from_db()
        self.assertEqual(
            provider.roles,
            data['providers-0-roles'].split(','),
            msg="Admin page wrong provider.roles after update"
        )

    def test_add_update_collection_with_link(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        collection, data, link = self._create_collection(with_link=True)[:3]

        # update some data in link
        data["links-INITIAL_FORMS"] = 1
        data["links-0-id"] = link.id
        data["links-0-collection"] = collection.id
        data["links-0-title"] = "New Title"
        response = self.client.post(
            f"/api/stac/admin/stac_api/collection/{collection.id}/change/", data
        )

        # Status code for successful update is 302, since in the admin UI
        # you're redirected to the list view after successful update
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update link")

        link.refresh_from_db()
        self.assertEqual(
            link.title, data['links-0-title'], msg="Admin page wrong link.title after update"
        )

    def test_add_collection_with_invalid_data(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        # Post data to create a new collection
        # Note: the *-*_FORMS fields are necessary management form fields
        # originating from the AdminInline and must be present
        data = {
            "name": "test collection invalid name",
            "license": "free",
            "description": "some very important collection",
            "title": "Test collection",
            "providers-TOTAL_FORMS": "0",
            "providers-INITIAL_FORMS": "0",
            "links-TOTAL_FORMS": "1",
            "links-INITIAL_FORMS": "0",
            "links-0-href": "www.example.com",
            "links-0-rel": "example",
            "links-0-link_type": "example",
            "links-0-title": "Example test",
        }
        response = self.client.post("/api/stac/admin/stac_api/collection/add/", data)

        # Status code for unsuccessful creation is 200, since in the admin UI
        # is returning an error message
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Collection.objects.filter(name=data["name"]).exists(),
            msg="Collection with invalid data has been added to db"
        )

    def test_add_update_collection_remove_provider(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        collection, data, link, provider = self._create_collection(with_provider=True)

        # remove provider
        data["providers-INITIAL_FORMS"] = 1
        data["providers-0-id"] = provider.id
        data["providers-0-collection"] = collection.id
        data["providers-0-DELETE"] = "on"
        response = self.client.post(
            f"/api/stac/admin/stac_api/collection/{collection.id}/change/", data
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove provider")
        self.assertFalse(
            Provider.objects.filter(collection=collection, name=data["providers-0-name"]).exists(),
            msg="Deleted provider still in DB"
        )

    def test_add_update_collection_remove_link(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        collection, data, link = self._create_collection(with_link=True)[:3]

        # remove provider
        data["links-INITIAL_FORMS"] = 1
        data["links-0-id"] = link.id
        data["links-0-collection"] = collection.id
        data["links-0-DELETE"] = "on"
        response = self.client.post(
            f"/api/stac/admin/stac_api/collection/{collection.id}/change/", data
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove link")
        self.assertFalse(
            CollectionLink.objects.filter(collection=collection, rel=data["links-0-rel"]).exists(),
            msg="Deleted link still in DB"
        )

    def test_add_remove_collection(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        collection, data, link, provider = self._create_collection(
            with_link=True,
            with_provider=True,
        )
        item = self._create_item(collection, with_link=True)[0]
        asset = self._create_asset(item)[0]

        # remove collection with links and providers
        response = self.client.post(
            f"/api/stac/admin/stac_api/collection/{collection.id}/delete/", {"post": "yes"}
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove collection")
        self.assertFalse(Asset.objects.filter(item=item).exists(), msg="Deleted asset still in DB")
        self.assertFalse(
            Item.objects.filter(collection=collection).exists(), msg="Deleted item still in DB"
        )
        self.assertFalse(
            ItemLink.objects.filter(item=item).exists(), msg="Deleted item link still in DB"
        )
        self.assertFalse(
            CollectionLink.objects.filter(collection=collection).exists(),
            msg="Deleted collection link still in DB"
        )
        self.assertFalse(
            Provider.objects.filter(collection=collection).exists(),
            msg="Deleted provider still in DB"
        )
        self.assertFalse(
            Collection.objects.filter(name=data["name"]).exists(),
            msg="Admin page collection still in DB"
        )


#--------------------------------------------------------------------------------------------------


class AdminItemTestCase(AdminBaseTestCase):

    def setUp(self):
        super().setUp()
        self._setup(create_collection=True)

    def test_add_update_item(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        item, data = self._create_item(self.collection)[:2]

        # update some data
        data['properties_title'] = "New title"
        response = self.client.post(f"/api/stac/admin/stac_api/item/{item.id}/change/", data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update item")
        item.refresh_from_db()
        self.assertEqual(
            item.properties_title,
            data['properties_title'],
            msg="Admin page item properties_title update did not work"
        )

    def test_add_update_item_with_link(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        item, data, link = self._create_item(self.collection, with_link=True)

        # update some data
        data['properties_title'] = "New title"
        data["links-INITIAL_FORMS"] = 1
        data["links-0-id"] = link.id
        data["links-0-item"] = item.id
        data["links-0-link_type"] = "New type"
        response = self.client.post(f"/api/stac/admin/stac_api/item/{item.id}/change/", data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update item")
        item.refresh_from_db()
        self.assertEqual(
            item.properties_title,
            data['properties_title'],
            msg="Admin page item properties_title update did not work"
        )
        link.refresh_from_db()
        self.assertEqual(
            link.link_type,
            data['links-0-link_type'],
            msg="Admin page wrong link.link_type after update"
        )

    def test_add_item_with_invalid_data(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        # Post data to create a new item
        # Note: the *-*_FORMS fields are necessary management form fields
        # originating from the AdminInline and must be present
        data = {
            "collection": self.collection.id,
            "name": "test item invalid name",
            "links-TOTAL_FORMS": "0",
            "links-INITIAL_FORMS": "0",
        }
        response = self.client.post("/api/stac/admin/stac_api/item/add/", data)

        # Status code for unsuccessful creation is 200, since in the admin UI
        # is returning an error message
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Item.objects.filter(collection=self.collection, name=data["name"]).exists(),
            msg="Item with invalid data has been added to db"
        )

    def test_add_update_item_remove_link(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        item, data, link = self._create_item(self.collection, with_link=True)

        # remove provider
        data["links-INITIAL_FORMS"] = 1
        data["links-0-id"] = link.id
        data["links-0-item"] = item.id
        data["links-0-DELETE"] = "on"
        response = self.client.post(f"/api/stac/admin/stac_api/item/{item.id}/change/", data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove link")
        self.assertFalse(
            ItemLink.objects.filter(item=item, rel=data["links-0-rel"]).exists(),
            msg="Deleted link still in DB"
        )

    def test_add_remove_item(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        item, data, link = self._create_item(self.collection, with_link=True)

        # remove item with links
        response = self.client.post(
            f"/api/stac/admin/stac_api/item/{item.id}/delete/", {"post": "yes"}
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove item")
        self.assertFalse(
            ItemLink.objects.filter(item=item, rel=data["links-0-rel"]).exists(),
            msg="Deleted link still in DB"
        )
        self.assertFalse(
            Item.objects.filter(name=data["name"]).exists(), msg="Admin page item still in DB"
        )


#--------------------------------------------------------------------------------------------------


class AdminAssetTestCase(AdminBaseTestCase):

    def setUp(self):
        super().setUp()
        self._setup(create_collection=True, create_item=True)

    def test_add_update_asset(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        asset, data = self._create_asset(self.item)

        # update some data
        data["checksum_multihash"] = "fffffffffffffffffff"
        data["description"] = "This is a new description"
        data["eo_gsd"] = 20
        data["geoadmin_lang"] = "fr"
        data["geoadmin_variant"] = "kombs"
        data["proj_epsg"] = 2057
        data["title"] = "New Asset for test"
        data["media_type"] = "application/x.asc+zip"
        data["href"] = "http://www.new-example.com"
        response = self.client.post(f"/api/stac/admin/stac_api/asset/{asset.id}/change/", data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update asset")
        asset.refresh_from_db()
        for key, value in data.items():
            if key in ['item', 'id']:
                continue
            self.assertEqual(getattr(asset, key), value, msg=f"Failed to update field {key}")

    def test_add_asset_with_invalid_data(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        data = {
            "item": self.item.id,
            "name": "test asset invalid name",
        }
        response = self.client.post("/api/stac/admin/stac_api/asset/add/", data)

        # Status code for unsuccessful creation is 200, since in the admin UI
        # is returning an error message
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Asset.objects.filter(item=self.item, name=data["name"]).exists(),
            msg="Asset with invalid data has been added to db"
        )

    def test_add_remove_asset(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        asset, data = self._create_asset(self.item)

        # remove asset
        response = self.client.post(
            f"/api/stac/admin/stac_api/asset/{asset.id}/delete/", {"post": "yes"}
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove asset")
        self.assertFalse(
            Asset.objects.filter(name=data["name"]).exists(), msg="Admin page asset still in DB"
        )
