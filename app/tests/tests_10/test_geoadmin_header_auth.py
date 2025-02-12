import logging

from parameterized import parameterized

from django.contrib.auth import get_user_model
from django.test import Client
from django.test import override_settings

from tests.tests_10.base_test import STAC_BASE_V
from tests.tests_10.base_test import StacBaseTestCase
from tests.tests_10.data_factory import Factory

logger = logging.getLogger(__name__)


@override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
class GeoadminHeadersAuthForPutEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client(enforce_csrf_checks=True)
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample()
        get_user_model().objects.create_user("user")
        get_user_model().objects.create_superuser("superuser")

    @parameterized.expand([
        ("newuser", "true", 201),
        ("newuser", "false", 401),
        ("newuser", "", 401),
        ("user", "true", 201),
        ("user", "false", 401),
        ("user", "", 401),
        ("superuser", "true", 201),
        ("superuser", "false", 401),
        ("superuser", "", 401),
        (None, None, 401),
        (None, "false", 401),
        (None, "true", 401),
    ])
    def test_collection_upsert_create_with_geoadmin_header_auth(
        self, username_header, authenticated_header, expected_response_code
    ):
        new_user = username_header not in ("user", "superuser")
        if new_user:
            # make sure users don't exists already
            user = get_user_model().objects.filter(username=username_header).first()
            self.assertTrue(user is None)

        sample = self.factory.create_collection_sample(sample='collection-2')

        headers = None
        if username_header or authenticated_header:
            headers = {
                "Geoadmin-Username": username_header,
                "Geoadmin-Authenticated": authenticated_header,
            }

        response = self.client.put(
            path=f"/{STAC_BASE_V}/collections/{sample['name']}",
            data=sample.get_json('put'),
            content_type='application/json',
            headers=headers,
        )
        self.assertStatusCode(expected_response_code, response)

        if 200 <= expected_response_code < 300:
            self.check_stac_collection(sample.json, response.json())

            # user should have been promoted to superusers
            user = get_user_model().objects.filter(username=username_header).first()
            self.assertTrue(user is not None)
            self.assertTrue(user.is_superuser)

        else:
            if new_user:
                # non-existing users should not have been created
                user = get_user_model().objects.filter(username=username_header).first()
                self.assertTrue(user is None)

            if username_header == "user":
                # existing users should not have been promoted to superusers
                user = get_user_model().objects.filter(username=username_header).first()
                self.assertTrue(user is not None)
                self.assertFalse(user.is_superuser)
