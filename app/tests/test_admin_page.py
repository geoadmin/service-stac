from stac_api.models import Collection
from django.contrib.auth.models import User
from django.test import Client
from django.test import TestCase


class AdminTestCase(TestCase):

    def setUp(self):
        self.password = 'sesam'
        self.username = 'admin_user'
        self.admin_user = User.objects.create_superuser(
            self.username, 'myemail@test.com', self.password)
        self.client = Client()

    def test_admin_page(self):
        # very simple test to check if the admin page login is up
        response = self.client.get("/api/stac/admin/login/?next=/api/stac/admin")
        self.assertEqual(response.status_code, 200, "Admin page login not up.")

    def test_login(self):
        # Make sure login of the test user works
        self.client.login(username=self.username, password=self.password)
        response = self.client.get("/api/stac/admin")
        self.assertEqual(response.status_code, 301)

    def test_add_collection(self):
        # Login the user first
        self.client.login(username=self.username, password=self.password)

        # Post data to create a new collection
        # Note: the *-*_FORMS fields are necessary mgmt form fields
        # originating from the AdminInline and must be present
        response = self.client.post("/api/stac/admin/stac_api/collection/add/", {
            "name": "test_collection",
            "license": "free",
            "description": "some very important collection",
            "providers-TOTAL_FORMS": "0",
            "providers-INITIAL_FORMS": "0",
            "links-TOTAL_FORMS": "0",
            "links-INITIAL_FORMS": "0"
        })

        # Status code for successful creation is 302, since in the admin UI
        # you're redirected to the list view after successful creation
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Collection.objects.filter(name="test_collection").exists())
