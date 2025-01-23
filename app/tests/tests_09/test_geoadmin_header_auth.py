import logging

from parameterized import parameterized

from django.contrib.auth import get_user_model
from django.test import Client
from django.test import override_settings

from tests.tests_09.base_test import STAC_BASE_V
from tests.tests_09.base_test import StacBaseTestCase
from tests.tests_09.data_factory import Factory

logger = logging.getLogger(__name__)


@override_settings(FEATURE_AUTH_ENABLE_APIGW=True)
class GeoadminHeadersAuthForPutEndpointTestCase(StacBaseTestCase):
    valid_username = "another_test_user"

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client(enforce_csrf_checks=True)
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample()
        get_user_model().objects.create_superuser(self.valid_username)

    @parameterized.expand([
        (valid_username, "true", 201),
        (None, None, 401),
        (valid_username, "false", 401),
        ("wronguser", "true", 403),
    ])
    def test_collection_upsert_create_with_geoadmin_header_auth(
        self, username_header, authenticated_header, expected_response_code
    ):
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
