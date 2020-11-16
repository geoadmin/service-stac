from django.test import Client
from django.test import TestCase

class AdminTestCase(TestCase):

    def setUp(self):
        self.client = Client()

    def test_admin_page(self):
        # very simple test to check if the admin page login is up
        response = self.client.get(f"/api/stac/admin/login/?next=/api/stac/admin")
        print(response)
        self.assertEqual(response.status_code, 200)
