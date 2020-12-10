from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework.test import APIRequestFactory

API_BASE = settings.API_BASE


class GetTokenEndpointTestCase(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.factory = APIRequestFactory()
        self.username = 'SherlockHolmes'
        self.password = '221B_BakerStreet'
        self.user = get_user_model().objects.create_user(
            self.username, 'top@secret.co.uk', self.password
        )
        self.user.save()

    def test_get_token_with_valid_credentials(self):
        url = reverse('get_token')
        response = self.client.post(url, {'username': self.username, 'password': self.password})
        self.assertEqual(200, response.status_code, msg="User request for token failed.")
        generated_token = response.data["token"]
        token_from_db = Token.objects.get(user=self.user)
        self.assertEqual(
            generated_token,
            token_from_db.key,
            msg="Generated token and token stored in DB do not match."
        )
