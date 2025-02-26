import logging
from io import BytesIO

from django.conf import settings
from django.test import override_settings
from django.urls import reverse

from stac_api.management.commands.test_asset_upload import TestAssetUploadHandler
from stac_api.models.collection import Collection
from stac_api.models.collection import CollectionLink
from stac_api.models.general import Provider
from stac_api.models.item import Asset
from stac_api.models.item import Item
from stac_api.models.item import ItemLink
from stac_api.utils import parse_multihash

from tests.base_test_admin_page import AdminBaseTestCase
from tests.utils import S3TestMixin
from tests.utils import mock_s3_asset_file

logger = logging.getLogger(__name__)

#--------------------------------------------------------------------------------------------------


class AdminTestCase(AdminBaseTestCase):

    def test_admin_page(self):
        # very simple test to check if the admin page login is up
        response = self.client.get("/api/stac/admin/login/?next=/api/stac/admin")
        self.assertEqual(response.status_code, 200, "Admin page login not up.")

    def test_login(self):
        # Make sure login of the test user works
        self.client.login(username=self.username, password=self.password)
        response = self.client.get("/api/stac/admin/")
        self.assertEqual(response.status_code, 200, msg="Admin page login failed")

    def test_login_noslash(self):
        self.client.login(username=self.username, password=self.password)
        response = self.client.get("/api/stac/admin")
        self.assertEqual(response.status_code, 301, msg="Admin page redirection failed")
        self.assertEqual("/api/stac/admin/", response.url)

    def test_login_failure(self):
        # Make sure login with wrong password fails
        self.client.login(username=self.username, password="wrongpassword")
        response = self.client.get("/api/stac/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual("/api/stac/admin/login/?next=/api/stac/admin/", response.url)

    def test_login_header_disabled(self):
        response = self.client.get(
            "/api/stac/admin/",
            headers={
                "Geoadmin-Username": self.username, "Geoadmin-Authenticated": "true"
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual("/api/stac/admin/login/?next=/api/stac/admin/", response.url)

    @override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
    def test_login_header(self):
        response = self.client.get(
            "/api/stac/admin/",
            headers={
                "Geoadmin-Username": self.username, "Geoadmin-Authenticated": "true"
            }
        )
        self.assertEqual(response.status_code, 200, msg="Admin page login with header failed")

    @override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
    def test_login_header_noheader(self):
        response = self.client.get("/api/stac/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual("/api/stac/admin/login/?next=/api/stac/admin/", response.url)

    @override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
    def test_login_header_wronguser(self):
        response = self.client.get(
            "/api/stac/admin/",
            headers={
                "Geoadmin-Username": "wronguser", "Geoadmin-Authenticated": "true"
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual("/api/stac/admin/login/?next=/api/stac/admin/", response.url)

    @override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
    def test_login_header_not_authenticated(self):
        self.assertNotIn("sessionid", self.client.cookies)
        response = self.client.get(
            "/api/stac/admin/",
            headers={
                "Geoadmin-Username": self.username, "Geoadmin-Authenticated": "false"
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual("/api/stac/admin/login/?next=/api/stac/admin/", response.url)

    @override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
    def test_login_header_session(self):
        self.assertNotIn("sessionid", self.client.cookies)

        # log in with the header
        response = self.client.get(
            "/api/stac/admin/",
            headers={
                "Geoadmin-Username": self.username, "Geoadmin-Authenticated": "true"
            }
        )
        self.assertEqual(response.status_code, 200, msg="Admin page login with header failed")
        self.assertIn("sessionid", self.client.cookies)

        # verify we still have access just with the session cookie (no header)
        response = self.client.get("/api/stac/admin/")
        self.assertEqual(
            response.status_code, 200, msg="Unable to load admin page with session cookie"
        )

        # verify we still have access just with the session cookie and invalid headers
        response = self.client.get(
            "/api/stac/admin/",
            headers={
                "Geoadmin-Username": " ", "Geoadmin-Authenticated": "false"
            }
        )
        self.assertEqual(
            response.status_code,
            200,
            msg=(
                "Unable to load admin page with session cookie" +
                " and empty Geoadmin-Username header"
            )
        )

        # verify we lose access when we set an invalid user with valid headers
        response = self.client.get(
            "/api/stac/admin/",
            headers={
                "Geoadmin-Username": "wronguser", "Geoadmin-Authenticated": "true"
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual("/api/stac/admin/login/?next=/api/stac/admin/", response.url)


#--------------------------------------------------------------------------------------------------


class AdminCollectionTestCase(AdminBaseTestCase):

    def setUp(self):
        super().setUp()
        self.client.login(username=self.username, password=self.password)

    def test_add_update_collection(self):
        collection, data = self._create_collection()[:2]

        # update some data
        data['title'] = "New title"
        response = self.client.post(
            reverse('admin:stac_api_collection_change', args=[collection.id]), data
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update collection")
        collection.refresh_from_db()
        self.assertEqual(
            collection.title, data['title'], msg="Admin page collection title update did not work"
        )

    def test_publish_collection(self):
        collection, data = self._create_collection()[:2]

        # By default collection should be published
        self.assertTrue(collection.published, msg="Admin page default collection is not published")

        # un published the collection
        data.pop('published')
        response = self.client.post(
            reverse('admin:stac_api_collection_change', args=[collection.id]), data
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update collection")
        collection.refresh_from_db()
        # collection = Collection.objects.get(name=data['name'])
        self.assertFalse(collection.published, msg="Admin page collection still published")

        # Publish the collection again
        data['published'] = "on"
        response = self.client.post(
            reverse('admin:stac_api_collection_change', args=[collection.id]), data
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update collection")
        collection.refresh_from_db()
        # collection = Collection.objects.get(name=data['name'])
        self.assertTrue(collection.published, msg="Admin page collection still unpublished")

    def test_add_update_collection_with_provider(self):
        collection, data, link, provider = self._create_collection(with_provider=True)

        # update some data in provider
        data["providers-INITIAL_FORMS"] = 1
        data["providers-0-id"] = provider.id
        data["providers-0-collection"] = collection.id
        data["providers-0-roles"] = "licensor,producer"
        response = self.client.post(
            reverse('admin:stac_api_collection_change', args=[collection.id]), data
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

    def test_add_collection_with_provider_empty_description(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        data = {
            "name": "test_collection",
            "license": "free",
            "description": "some very important collection",
            "links-TOTAL_FORMS": "0",
            "links-INITIAL_FORMS": "0",
            "providers-TOTAL_FORMS": "1",
            "providers-INITIAL_FORMS": "0",
            "providers-0-name": "my-provider",
            "providers-0-description": "",
            "providers-0-roles": "licensor",
            "providers-0-url": "http://www.example.com",
            "assets-TOTAL_FORMS": "0",
            "assets-INITIAL_FORMS": "0"
        }
        response = self.client.post("/api/stac/admin/stac_api/collection/add/", data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to add new collection")
        self.assertTrue(
            Collection.objects.filter(name=data["name"]).exists(),
            msg="Admin page collection added not found in DB"
        )
        collection = Collection.objects.get(name=data["name"])

        self.assertTrue(
            Provider.objects.filter(collection=collection, name=data["providers-0-name"]).exists(),
            msg="Admin page Provider added not found in DB"
        )
        provider = Provider.objects.get(collection=collection, name=data["providers-0-name"])

        self.assertEqual(
            provider.description, None, msg="Admin page wrong provider.description on creation"
        )

    def test_add_update_collection_empty_provider_description(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        collection, data, link, provider = self._create_collection(with_provider=True)

        self.assertEqual(
            provider.description,
            data['providers-0-description'],
            msg="description non existent when it should exist."
        )

        # update some data in provider
        data["providers-INITIAL_FORMS"] = 1
        data["providers-0-id"] = provider.id
        data["providers-0-collection"] = collection.id
        data["providers-0-description"] = ""
        response = self.client.post(
            f"/api/stac/admin/stac_api/collection/{collection.id}/change/", data
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update provider")

        provider.refresh_from_db()
        self.assertEqual(
            provider.description,
            None,
            msg="Admin page wrong provider.description after update. Should be None"
        )

    def test_add_update_collection_with_link(self):
        collection, data, link = self._create_collection(with_link=True)[:3]

        # update some data in link
        data["links-INITIAL_FORMS"] = 1
        data["links-0-id"] = link.id
        data["links-0-collection"] = collection.id
        data["links-0-title"] = "New Title"
        response = self.client.post(
            reverse('admin:stac_api_collection_change', args=[collection.id]), data
        )

        # Status code for successful update is 302, since in the admin UI
        # you're redirected to the list view after successful update
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update link")

        link.refresh_from_db()
        self.assertEqual(
            link.title, data['links-0-title'], msg="Admin page wrong link.title after update"
        )

    def test_add_collection_with_invalid_data(self):
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
        response = self.client.post(reverse('admin:stac_api_collection_add'), data)

        # Status code for unsuccessful creation is 200, since in the admin UI
        # is returning an error message
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Collection.objects.filter(name=data["name"]).exists(),
            msg="Collection with invalid data has been added to db"
        )

    def test_add_update_collection_remove_provider(self):
        collection, data, link, provider = self._create_collection(with_provider=True)

        # remove provider
        data["providers-INITIAL_FORMS"] = 1
        data["providers-0-id"] = provider.id
        data["providers-0-collection"] = collection.id
        data["providers-0-DELETE"] = "on"
        response = self.client.post(
            reverse('admin:stac_api_collection_change', args=[collection.id]), data
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove provider")
        self.assertFalse(
            Provider.objects.filter(collection=collection, name=data["providers-0-name"]).exists(),
            msg="Deleted provider still in DB"
        )

    def test_add_update_collection_remove_link(self):
        collection, data, link = self._create_collection(with_link=True)[:3]

        # remove provider
        data["links-INITIAL_FORMS"] = 1
        data["links-0-id"] = link.id
        data["links-0-collection"] = collection.id
        data["links-0-DELETE"] = "on"
        response = self.client.post(
            reverse('admin:stac_api_collection_change', args=[collection.id]), data
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove link")
        self.assertFalse(
            CollectionLink.objects.filter(collection=collection, rel=data["links-0-rel"]).exists(),
            msg="Deleted link still in DB"
        )

    @mock_s3_asset_file
    def test_add_remove_collection(self):
        collection, data, link, provider = self._create_collection(
            with_link=True,
            with_provider=True,
        )
        item = self._create_item(collection, with_link=True)[0]
        asset = self._create_asset(item)[0]

        # remove collection with links and providers
        response = self.client.post(
            reverse('admin:stac_api_collection_delete', args=[collection.id]), {"post": "yes"}
        )

        # Removing a collection with items should not be allowed, note on failure a 200 OK is
        # returned with error description as html. In case of success a 302 is returned
        self.assertEqual(response.status_code, 200, msg="Admin page remove collection was allowed")

        # removes the assets and items first
        response = self.client.post(
            reverse('admin:stac_api_asset_delete', args=[asset.id]), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove asset")
        response = self.client.post(
            reverse('admin:stac_api_item_delete', args=[item.id]), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove item")

        # remove collection again with links and providers
        response = self.client.post(
            reverse('admin:stac_api_collection_delete', args=[collection.id]), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove collection")

        # Check that asset, item, links, providers doesn't exists anymore
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
        self.client.login(username=self.username, password=self.password)

    def test_add_update_item(self):
        item, data = self._create_item(self.collection)[:2]

        # update some data
        data['properties_title'] = "New title"
        response = self.client.post(reverse('admin:stac_api_item_change', args=[item.id]), data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update item")
        item.refresh_from_db()
        self.assertEqual(
            item.properties_title,
            data['properties_title'],
            msg="Admin page item properties_title update did not work"
        )

    def test_add_item_with_non_standard_projection(self):
        geometry = "SRID=4326;POLYGON ((6.1467996909879385 46.0441091039831, "\
            "7.438647976247291 46.0515315818849, 7.43863242087181 46.95108277187109, "\
                "6.1251436509289805 46.943536997721836, 6.1467996909879385 46.0441091039831))"
        text_geometry = "SRID=2056;POLYGON ((2500000 1100000, 2600000 1100000, 2600000 1200000, "\
            "2500000 1200000, 2500000 1100000))"
        post_data = {
            "collection": self.collection.id,
            "name": "test_item",
            "geometry": geometry,
            "text_geometry": text_geometry,
            "properties_datetime_0": "2020-12-01",
            "properties_datetime_1": "13:15:39",
            "properties_title": "test",
            "links-TOTAL_FORMS": "0",
            "links-INITIAL_FORMS": "0",
        }
        #if transformed text_geometry does not match the geometry provided the creation will fail
        self._create_item(self.collection, data=post_data)[:2]  # pylint: disable=expression-not-assigned

    def test_add_update_item_remove_title(self):
        item, data = self._create_item(self.collection)[:2]

        # remove the title
        data['properties_title'] = ""
        response = self.client.post(reverse('admin:stac_api_item_change', args=[item.id]), data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update item")
        item.refresh_from_db()
        self.assertEqual(
            item.properties_title, None, msg="Admin page item properties_title update did not work"
        )

    def test_add_update_item_with_link(self):
        item, data, link = self._create_item(self.collection, with_link=True)

        # update some data
        data['properties_title'] = "New title"
        data["links-INITIAL_FORMS"] = 1
        data["links-0-id"] = link.id
        data["links-0-item"] = item.id
        data["links-0-link_type"] = "New type"
        response = self.client.post(reverse('admin:stac_api_item_change', args=[item.id]), data)

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
        # Post data to create a new item
        # Note: the *-*_FORMS fields are necessary management form fields
        # originating from the AdminInline and must be present
        data = {
            "collection": self.collection.id,
            "name": "test item invalid name",
            "links-TOTAL_FORMS": "0",
            "links-INITIAL_FORMS": "0",
        }
        response = self.client.post(reverse('admin:stac_api_item_add'), data)

        # Status code for unsuccessful creation is 200, since in the admin UI
        # is returning an error message
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Item.objects.filter(collection=self.collection, name=data["name"]).exists(),
            msg="Item with invalid data has been added to db"
        )

    def test_add_update_item_remove_link(self):
        item, data, link = self._create_item(self.collection, with_link=True)

        # remove provider
        data["links-INITIAL_FORMS"] = 1
        data["links-0-id"] = link.id
        data["links-0-item"] = item.id
        data["links-0-DELETE"] = "on"
        response = self.client.post(reverse('admin:stac_api_item_change', args=[item.id]), data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove link")
        self.assertFalse(
            ItemLink.objects.filter(item=item, rel=data["links-0-rel"]).exists(),
            msg="Deleted link still in DB"
        )

    @mock_s3_asset_file
    def test_add_remove_item(self):
        item, data, link = self._create_item(self.collection, with_link=True)
        asset = self._create_asset(item)[0]

        # remove item with links
        response = self.client.post(
            reverse('admin:stac_api_item_delete', args=[item.id]), {"post": "yes"}
        )

        # Removing items with assets should not be allowed, note on failure a 200 OK is returned
        # with error description as html. In case of success a 302 is returned
        self.assertEqual(response.status_code, 200, msg="Admin page remove item was allowed")

        # remove assets first
        response = self.client.post(
            reverse('admin:stac_api_asset_delete', args=[asset.id]), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove asset")

        # remove item again with links and providers
        response = self.client.post(
            reverse('admin:stac_api_item_delete', args=[item.id]), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove item")

        # Check that asset and links doesn't exist anymore
        self.assertFalse(Asset.objects.filter(item=item).exists(), msg="Deleted asset still in DB")
        self.assertFalse(
            ItemLink.objects.filter(item=item, rel=data["links-0-rel"]).exists(),
            msg="Deleted link still in DB"
        )
        self.assertFalse(
            Item.objects.filter(name=data["name"]).exists(), msg="Admin page item still in DB"
        )


#--------------------------------------------------------------------------------------------------


class AdminAssetTestCase(AdminBaseTestCase, S3TestMixin):

    def setUp(self):
        super().setUp()
        self._setup(create_collection=True, create_item=True)

        self.client.login(username=self.username, password=self.password)

    @mock_s3_asset_file
    def test_add_asset_minimal(self):
        self._create_asset_minimal(self.item)

    @mock_s3_asset_file
    def test_add_update_asset(self):

        asset, data = self._create_asset(self.item)

        filecontent = b'mybinarydata2'
        filelike = BytesIO(filecontent)
        filelike.name = 'testname.tiff'

        # update some data
        data["description"] = "This is a new description"
        data["eo_gsd"] = 20
        data["geoadmin_lang"] = "fr"
        data["geoadmin_variant"] = "kombs"
        data["proj_epsg"] = 2057
        data["title"] = "New Asset for test"
        data["media_type"] = "application/x.ascii-grid+zip"
        data["file"] = filelike
        response = self.client.post(reverse('admin:stac_api_asset_change', args=[asset.id]), data)

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to update asset")
        asset.refresh_from_db()
        for key, value in data.items():
            if key in ['item', 'id', 'file']:
                continue
            self.assertEqual(getattr(asset, key), value, msg=f"Failed to update field {key}")

        # Check that file content has changed
        with asset.file.open() as fd:
            self.assertEqual(filecontent, fd.read())

    def test_add_asset_with_invalid_data(self):

        data = {
            "item": self.item.id,
            "name": "test asset invalid name",
        }
        response = self.client.post(reverse('admin:stac_api_asset_add'), data)

        # Status code for unsuccessful creation is 200, since in the admin UI
        # is returning an error message
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Asset.objects.filter(item=self.item, name=data["name"]).exists(),
            msg="Asset with invalid data has been added to db"
        )

    @mock_s3_asset_file
    def test_add_remove_asset(self):

        asset, data = self._create_asset(self.item)
        path = f"{asset.item.collection.name}/{asset.item.name}/{data['name']}"
        self.assertS3ObjectExists(path)

        # remove asset
        response = self.client.post(
            reverse('admin:stac_api_asset_delete', args=[asset.id]), {"post": "yes"}
        )

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302, msg="Admin page failed to remove asset")
        self.assertFalse(
            Asset.objects.filter(name=data["name"]).exists(), msg="Admin page asset still in DB"
        )

        self.assertS3ObjectNotExists(path)

    @mock_s3_asset_file
    def test_add_update_asset_invalid_media_type(self):
        sample = self.factory.create_asset_sample(
            self.item, name='asset.txt', media_type='image/tiff; application=geotiff'
        ).attributes
        # Admin page doesn't uses the name for foreign key but the internal db id.
        sample['item'] = self.item.id
        response = self.client.post(reverse('admin:stac_api_asset_add'), sample)
        # Status code for unsuccessful creation is 200, since in the admin UI
        # is returning an error message
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Asset.objects.filter(item=self.item, name=sample["name"]).exists(),
            msg="Asset with invalid data has been added to db"
        )

    @mock_s3_asset_file
    def test_asset_file_metadata(self):
        content_type = 'image/tiff; application=geotiff'

        data = {"item": self.item.id, "name": "checksum.tiff", "media_type": content_type}

        response = self.client.post(reverse('admin:stac_api_asset_add'), data)
        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Asset.objects.filter(item=self.item, name=data["name"]).exists(),
            msg="Admin page asset added not found in DB"
        )
        asset = Asset.objects.get(item=self.item, name=data["name"])

        filecontent = b'mybinarydata2'
        filelike = BytesIO(filecontent)
        filelike.name = 'checksum.tiff'

        data.update({
            "item": self.item.id,
            "description": "",
            "eo_gsd": "",
            "geoadmin_lang": "",
            "geoadmin_variant": "",
            "proj_epsg": "",
            "title": "",
            "file": filelike
        })

        response = self.client.post(reverse('admin:stac_api_asset_change', args=[asset.id]), data)
        asset.refresh_from_db()

        credentials = {'username': self.username, 'password': self.password}

        handler = TestAssetUploadHandler("http://localhost:8000", credentials)
        handler.start(self.item, asset, filelike)

        path = f"{self.item.collection.name}/{self.item.name}/{data['name']}"

        logger.info(
            f"Asset at present: {asset} at path : {path} with checksum : {asset.checksum_multihash}"
        )
        sha256 = parse_multihash(asset.checksum_multihash).digest.hex()
        obj = self.get_s3_object(path)
        logger.info(f"Object: {obj}")
        self.assertS3ObjectContentType(obj, path, content_type)
        self.assertS3ObjectSha256(obj, path, sha256)
        self.assertS3ObjectCacheControl(obj, path, max_age=settings.STORAGE_ASSETS_CACHE_SECONDS)

    @mock_s3_asset_file
    def test_asset_custom_upload(self):

        asset, _ = self._create_asset(self.item)
        # Need to set a csrf token so there is a token to pass to the template.
        # The actual token value does not matter.
        self.client.cookies["csrftoken"] = "some_token_value"
        response = self.client.get(reverse('admin:stac_api_asset_upload', args=[asset.id]))
        self.assertEqual(response.status_code, 200, msg="Admin page login failed")
        self.assertContains(
            response,
            f"<h1>Upload file for {self.collection.name}/{self.item.name}/{asset.name}</h1>"
        )
