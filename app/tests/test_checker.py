import time

from django.test import Client
from django.test import TestCase
from django.test import override_settings


class CheckerTestCase(TestCase):

    def setUp(self):
        self.client = Client()

    def test_checker(self):
        response = self.client.get('/checker')
        self.assertEqual(response.status_code, 200)

    @override_settings(CHECKER_DELAY=2)
    def test_checker_delayed(self):
        start = time.time()
        response = self.client.get('/checker')
        end = time.time()
        self.assertEqual(response.status_code, 200)
        self.assertGreater(end, start + 2, f'Expected at least 2s, only took {end - start}')
