# Deactivate healthcheck test as endpoint is also deactivated

# from config.settings import HEALTHCHECK_ENDPOINT
# from config.settings import STAC_BASE

# from django.test import Client
# from django.test import TestCase

# class HealthCheckTestCase(TestCase):

#     def setUp(self):
#         self.client = Client()

#     def test_healthcheck(self):
#         response = self.client.get(f"/{STAC_BASE}/{HEALTHCHECK_ENDPOINT}")
#         self.assertEqual(response.status_code, 200)
#         self.assertEqual(response['Content-Type'], 'application/json')
#         self.assertIn('no-cache', response['Cache-control'])
