import logging
from datetime import datetime

from django.conf import settings
from django.test import Client

from stac_api.utils import utc_aware

from tests.base_test import StacBaseTestCase
from tests.data_factory import CollectionFactory
from tests.utils import client_login

logger = logging.getLogger(__name__)

STAC_BASE_V = settings.STAC_BASE_V


class CollectionsEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        factory = CollectionFactory()
        self.collection_1 = factory.create_sample(sample='collection-1', db_create=True)
        self.collection_2 = factory.create_sample(sample='collection-2', db_create=True)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_collections_endpoint(self):
        response = self.client.get(f"/{STAC_BASE_V}/collections")
        response_json = response.json()
        self.assertStatusCode(200, response)

        self.check_stac_collection(self.collection_1.json, response_json['collections'][0])
        self.check_stac_collection(self.collection_2.json, response_json['collections'][1])

    def test_single_collection_endpoint(self):
        collection_name = self.collection_1.attributes['name']
        response = self.client.get(f"/{STAC_BASE_V}/collections/{collection_name}")
        response_json = response.json()
        self.assertStatusCode(200, response)
        # The ETag change between each test call due to the created, updated time that are in the
        # hash computation of the ETag
        self.check_header_etag(None, response)

        self.check_stac_collection(self.collection_1.json, response_json)

    def test_collections_limit_query(self):
        response = self.client.get(f"/{STAC_BASE_V}/collections?limit=1")
        self.assertStatusCode(200, response)
        self.assertLessEqual(1, len(response.json()['collections']))

        response = self.client.get(f"/{STAC_BASE_V}/collections?limit=0")
        self.assertStatusCode(400, response)
        self.assertEqual(['limit query parameter to small, must be in range 1..100'],
                         response.json()['description'],
                         msg='Unexpected error message')

        response = self.client.get(f"/{STAC_BASE_V}/collections?limit=test")
        self.assertStatusCode(400, response)
        self.assertEqual(['invalid limit query parameter: must be an integer'],
                         response.json()['description'],
                         msg='Unexpected error message')

        response = self.client.get(f"/{STAC_BASE_V}/collections?limit=-1")
        self.assertStatusCode(400, response)
        self.assertEqual(['limit query parameter to small, must be in range 1..100'],
                         response.json()['description'],
                         msg='Unexpected error message')

        response = self.client.get(f"/{STAC_BASE_V}/collections?limit=1000")
        self.assertStatusCode(400, response)
        self.assertEqual(['limit query parameter to big, must be in range 1..100'],
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_collection_non_allowed_parameters(self):
        non_allowed_parameter = "no_limits"
        value = 100
        response = self.client.get(f"/{STAC_BASE_V}/collections?{non_allowed_parameter}=100")
        self.assertStatusCode(400, response)
        json_data = response.json()
        self.assertIn(
            non_allowed_parameter,
            str(json_data['description']),
            msg=f"Wrong query parameter {non_allowed_parameter} not found in error message"
        )


class CollectionsWriteEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        client_login(self.client)
        self.collection_factory = CollectionFactory()
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_valid_collections_post(self):
        collection = self.collection_factory.create_sample()

        path = f"/{STAC_BASE_V}/collections"
        response = self.client.post(
            path, data=collection.get_json('post'), content_type='application/json'
        )
        self.assertStatusCode(201, response)
        self.check_header_location(f'{path}/{collection.json["id"]}', response)

        response = self.client.get(f"/{STAC_BASE_V}/collections/{collection.json['id']}")
        response_json = response.json()
        self.assertEqual(response_json['id'], collection.json['id'])
        self.check_stac_collection(collection.json, response.json())

        # the dataset already exists in the database
        response = self.client.post(
            f"/{STAC_BASE_V}/collections",
            data=collection.get_json('post'),
            content_type='application/json'
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'id': ['This field must be unique.']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_collections_post_extra_payload(self):
        collection = self.collection_factory.create_sample(extra_payload='not allowed')

        response = self.client.post(
            f"/{STAC_BASE_V}/collections",
            data=collection.get_json('post'),
            content_type='application/json'
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'extra_payload': ['Unexpected property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_collections_post_read_only_in_payload(self):
        collection = self.collection_factory.create_sample(created=utc_aware(datetime.utcnow()))

        response = self.client.post(
            f"/{STAC_BASE_V}/collections",
            data=collection.get_json('post', keep_read_only=True),
            content_type='application/json'
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'created': ['Found read-only property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_invalid_collections_post(self):
        # the dataset already exists in the database
        collection = self.collection_factory.create_sample(sample='collection-invalid')

        response = self.client.post(
            f"/{STAC_BASE_V}/collections",
            data=collection.get_json('post'),
            content_type='application/json'
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'license': ['Not a valid string.']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_collections_min_mandatory_post(self):
        # a post with the absolute valid minimum
        collection = self.collection_factory.create_sample(required_only=True)

        path = f"/{STAC_BASE_V}/collections"
        response = self.client.post(
            path, data=collection.get_json('post'), content_type='application/json'
        )
        response_json = response.json()
        logger.debug(response_json)
        self.assertStatusCode(201, response)
        self.check_header_location(f'{path}/{collection.json["id"]}', response)
        self.assertNotIn('title', response_json.keys())  # key does not exist
        self.assertNotIn('providers', response_json.keys())  # key does not exist
        self.check_stac_collection(collection.json, response_json)

    def test_collections_less_than_mandatory_post(self):
        # a post with the absolute valid minimum
        collection = self.collection_factory.create_sample(
            sample='collection-missing-mandatory-fields'
        )

        response = self.client.post(
            f"/{STAC_BASE_V}/collections",
            data=collection.get_json('post'),
            content_type='application/json'
        )
        self.assertStatusCode(400, response)
        self.assertEqual(
            {
                'description': ['This field is required.'],
                'license': ['This field is required.'],
            },
            response.json()['description'],
            msg='Unexpected error message',
        )


class CollectionsUpdateEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        client_login(self.client)
        self.collection_factory = CollectionFactory()
        self.collection = self.collection_factory.create_sample().model
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_collection_put_dont_exists(self):
        sample = self.collection_factory.create_sample(sample='collection-2')

        # the dataset to update does not exist yet
        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{sample['name']}",
            data=sample.get_json('put'),
            content_type='application/json'
        )
        self.assertStatusCode(404, response)

    def test_collections_put(self):
        sample = self.collection_factory.create_sample(
            name=self.collection.name, sample='collection-2'
        )

        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{sample['name']}",
            data=sample.get_json('put'),
            content_type='application/json'
        )

        self.assertStatusCode(200, response)

        # is it persistent?
        response = self.client.get(f"/{STAC_BASE_V}/collections/{sample['name']}")

        self.assertStatusCode(200, response)
        self.check_stac_collection(sample.json, response.json())

    def test_collections_put_extra_payload(self):
        sample = self.collection_factory.create_sample(
            name=self.collection.name, sample='collection-2', extra_payload='not valid'
        )

        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{sample['name']}",
            data=sample.get_json('put'),
            content_type='application/json'
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'extra_payload': ['Unexpected property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_collections_put_read_only_in_payload(self):
        sample = self.collection_factory.create_sample(
            name=self.collection.name, sample='collection-2', created=utc_aware(datetime.utcnow())
        )

        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{sample['name']}",
            data=sample.get_json('put', keep_read_only=True),
            content_type='application/json'
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'created': ['Found read-only property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_collection_put_change_id(self):
        sample = self.collection_factory.create_sample(
            name='new-collection-name', sample='collection-2'
        )

        # for the start, the id have to be different
        self.assertNotEqual(self.collection.name, sample['name'])
        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{self.collection.name}",
            data=sample.get_json('put'),
            content_type='application/json'
        )
        self.assertStatusCode(200, response)

        # check if id changed
        response = self.client.get(f"/{STAC_BASE_V}/collections/{sample['name']}")
        self.assertStatusCode(200, response)
        self.check_stac_collection(sample.json, response.json())

        # the old collection shouldn't exist any more
        response = self.client.get(f"/{STAC_BASE_V}/collections/{self.collection.name}")
        self.assertStatusCode(404, response)

    def test_collection_put_remove_optional_fields(self):
        collection_name = self.collection.name  # get a name that is registered in the service
        sample = self.collection_factory.create_sample(
            name=collection_name, sample='collection-1', required_only=True
        )

        # for the start, the collection[1] has to have a title
        self.assertNotEqual('', f'{self.collection.title}')
        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{sample['name']}",
            data=sample.get_json('put'),
            content_type='application/json'
        )
        self.assertStatusCode(200, response)
        response_json = response.json()
        self.assertNotIn('title', response_json.keys())  # key does not exist
        self.assertNotIn('providers', response_json.keys())  # key does not exist

    def test_collection_patch(self):
        collection_name = self.collection.name  # get a name that is registered in the service
        payload_json = {'license': 'open-source'}
        # for the start, the collection[1] has to have a different licence than the payload
        self.assertNotEqual(self.collection.license, payload_json['license'])
        # for start the payload has no description
        self.assertNotIn('title', payload_json.keys())

        response = self.client.patch(
            f"/{STAC_BASE_V}/collections/{collection_name}",
            data=payload_json,
            content_type='application/json'
        )
        self.assertStatusCode(200, response)
        response_json = response.json()
        # licence affected by patch
        self.assertEqual(payload_json['license'], response_json['license'])

        # description not affected by patch
        self.assertEqual(self.collection.description, response_json['description'])

    def test_collection_patch_extra_payload(self):
        collection_name = self.collection.name  # get a name that is registered in the service
        payload_json = {'license': 'open-source', 'extra_payload': True}
        # for the start, the collection[1] has to have a different licence than the payload
        self.assertNotEqual(self.collection.license, payload_json['license'])
        # for start the payload has no description
        response = self.client.patch(
            f"/{STAC_BASE_V}/collections/{collection_name}",
            data=payload_json,
            content_type='application/json'
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'extra_payload': ['Unexpected property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_collection_patch_read_only_in_payload(self):
        collection_name = self.collection.name  # get a name that is registered in the service
        payload_json = {'license': 'open-source', 'created': utc_aware(datetime.utcnow())}
        # for the start, the collection[1] has to have a different licence than the payload
        self.assertNotEqual(self.collection.license, payload_json['license'])
        response = self.client.patch(
            f"/{STAC_BASE_V}/collections/{collection_name}",
            data=payload_json,
            content_type='application/json'
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'created': ['Found read-only property in payload']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_authorized_collection_delete(self):
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}'
        response = self.client.delete(path)
        # Collection delete is not implemented (and currently not foreseen), hence
        # the status code should be 405. If it should get implemented in future
        # an unauthorized delete should get a status code of 401 (see test above).
        self.assertStatusCode(405, response, msg="unimplemented collection delete was permitted.")


class CollectionsUnauthorizeEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.collection_factory = CollectionFactory()
        self.collection = self.collection_factory.create_sample().model
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_unauthorized_collection_post_put_patch(self):
        # make sure POST fails for anonymous user:
        # a post with the absolute valid minimum
        sample = self.collection_factory.create_sample(sample='collection-2')

        response = self.client.post(
            f"/{STAC_BASE_V}/collections",
            data=sample.get_json('post'),
            content_type='application/json'
        )
        self.assertStatusCode(401, response, msg="Unauthorized post was permitted.")

        # make sure PUT fails for anonymous user:
        sample = self.collection_factory.create_sample(
            name=self.collection.name, sample='collection-2'
        )
        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{self.collection.name}",
            data=sample.get_json('put'),
            content_type='application/json'
        )
        self.assertStatusCode(401, response, msg="Unauthorized put was permitted.")

        # make sure PATCH fails for anonymous user:
        response = self.client.patch(
            f"/{STAC_BASE_V}/collections/{self.collection.name}",
            data=sample.get_json('patch'),
            content_type='application/json'
        )
        self.assertStatusCode(401, response, msg="Unauthorized patch was permitted.")

    def test_unauthorized_collection_delete(self):
        path = f'/{STAC_BASE_V}/collections/{self.collection.name}'
        response = self.client.delete(path)
        # Collection delete is not implemented (and currently not foreseen).
        # Status code here is 401, as user is unauthorized for write requests.
        # If logged-in, it should be 405, as DELETE for collections is not
        # implemented.
        self.assertStatusCode(
            401, response, msg="unauthorized and unimplemented collection delete was permitted."
        )
