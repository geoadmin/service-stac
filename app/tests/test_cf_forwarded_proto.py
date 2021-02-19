from django.conf import settings
from django.test import Client
from django.test import TestCase

STAC_BASE_V = settings.STAC_BASE_V


class CFForwardedProtoTestCase(TestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()

    def test_http_access(self):
        response = self.client.get(f"/{STAC_BASE_V}", HTTP_ACCEPT='application/json', follow=True)
        for link in response.json().get('links', []):
            self.assertTrue(link['href'].startswith('http'))

    def test_https_access(self):
        response = self.client.get(
            f"/{STAC_BASE_V}",
            HTTP_CLOUDFRONT_FORWARDED_PROTO='https',
            HTTP_ACCEPT='application/json',
            follow=True
        )
        for link in response.json().get('links', []):
            self.assertTrue(link['href'].startswith('https'))
