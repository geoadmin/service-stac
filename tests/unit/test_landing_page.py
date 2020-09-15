from django.test import TestCase
from django.test import Client


class IndexTestCase(TestCase):

    def setUp(self):
        self.client = Client()

    def test_landing_page(self):
        response = self.client.get('/api/stac/v0.9/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json()['id'], 'ch')
        self.assertEqual(response.json()['stac_version'], '0.9.0')
