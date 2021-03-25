import logging
from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from stac_api.utils import utc_aware

from tests.base_test import StacBaseTestCase
from tests.base_test import StacBaseTransactionTestCase
from tests.data_factory import CollectionFactory
from tests.utils import client_login
from tests.utils import disableLogger

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
        self.collection = self.collection_factory.create_sample(db_create=True)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_collection_upsert_create(self):
        sample = self.collection_factory.create_sample(sample='collection-2')

        # the dataset to update does not exist yet
        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{sample['name']}",
            data=sample.get_json('put'),
            content_type='application/json'
        )
        self.assertStatusCode(201, response)

        self.check_stac_collection(sample.json, response.json())

    def test_collections_put(self):
        sample = self.collection_factory.create_sample(
            name=self.collection['name'], sample='collection-2'
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
            name=self.collection['name'], sample='collection-2', extra_payload='not valid'
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
            name=self.collection['name'],
            sample='collection-2',
            created=utc_aware(datetime.utcnow())
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
        self.assertNotEqual(self.collection['name'], sample['name'])
        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{self.collection['name']}",
            data=sample.get_json('put'),
            content_type='application/json'
        )
        self.assertStatusCode(200, response)

        # check if id changed
        response = self.client.get(f"/{STAC_BASE_V}/collections/{sample['name']}")
        self.assertStatusCode(200, response)
        self.check_stac_collection(sample.json, response.json())

        # the old collection shouldn't exist any more
        response = self.client.get(f"/{STAC_BASE_V}/collections/{self.collection['name']}")
        self.assertStatusCode(404, response)

    def test_collection_put_remove_optional_fields(self):
        collection_name = self.collection['name']  # get a name that is registered in the service
        sample = self.collection_factory.create_sample(
            name=collection_name, sample='collection-1', required_only=True
        )

        # for the start, the collection[1] has to have a title
        self.assertNotEqual('', f'{self.collection["title"]}')
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
        collection_name = self.collection['name']  # get a name that is registered in the service
        payload_json = {'license': 'open-source'}
        # for the start, the collection[1] has to have a different licence than the payload
        self.assertNotEqual(self.collection["license"], payload_json['license'])
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
        self.assertEqual(self.collection["description"], response_json['description'])

    def test_collection_patch_extra_payload(self):
        collection_name = self.collection['name']  # get a name that is registered in the service
        payload_json = {'license': 'open-source', 'extra_payload': True}
        # for the start, the collection[1] has to have a different licence than the payload
        self.assertNotEqual(self.collection['license'], payload_json['license'])
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
        collection_name = self.collection['name']  # get a name that is registered in the service
        payload_json = {'license': 'open-source', 'created': utc_aware(datetime.utcnow())}
        # for the start, the collection[1] has to have a different licence than the payload
        self.assertNotEqual(self.collection['license'], payload_json['license'])
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
        path = f'/{STAC_BASE_V}/collections/{self.collection["name"]}'
        response = self.client.delete(path)
        # Collection delete is not implemented (and currently not foreseen), hence
        # the status code should be 405. If it should get implemented in future
        # an unauthorized delete should get a status code of 401 (see test above).
        self.assertStatusCode(405, response, msg="unimplemented collection delete was permitted.")

    def test_collection_atomic_upsert_create_500(self):
        sample = self.collection_factory.create_sample(sample='collection-2')

        # the dataset to update does not exist yet
        with self.settings(DEBUG_PROPAGATE_API_EXCEPTIONS=True), disableLogger('stac_api.apps'):
            response = self.client.put(
                reverse('test-collection-detail-http-500', args=[sample['name']]),
                data=sample.get_json('put'),
                content_type='application/json'
            )
        self.assertStatusCode(500, response)
        self.assertEqual(response.json()['description'], "AttributeError('test exception')")

        # Make sure that the ressource has not been created
        response = self.client.get(reverse('collection-detail', args=[sample['name']]))
        self.assertStatusCode(404, response)

    def test_collection_atomic_upsert_update_500(self):
        sample = self.collection_factory.create_sample(
            sample='collection-2', name=self.collection['name']
        )

        # Make sure samples is different from actual data
        self.assertNotEqual(sample.attributes, self.collection.attributes)

        # the dataset to update does not exist yet
        with self.settings(DEBUG_PROPAGATE_API_EXCEPTIONS=True), disableLogger('stac_api.apps'):
            # because we explicitely test a crash here we don't want to print a CRITICAL log on the
            # console therefore disable it.
            response = self.client.put(
                reverse('test-collection-detail-http-500', args=[sample['name']]),
                data=sample.get_json('put'),
                content_type='application/json'
            )
        self.assertStatusCode(500, response)
        self.assertEqual(response.json()['description'], "AttributeError('test exception')")

        # Make sure that the ressource has not been created
        response = self.client.get(reverse('collection-detail', args=[sample['name']]))
        self.assertStatusCode(200, response)
        self.check_stac_collection(self.collection.json, response.json())


class CollectionRaceConditionTest(StacBaseTransactionTestCase):

    def setUp(self):
        self.username = 'user'
        self.password = 'dummy-password'
        get_user_model().objects.create_superuser(self.username, password=self.password)

    def test_collection_upsert_race_condition(self):
        workers = 5
        status_201 = 0
        sample = CollectionFactory().create_sample(sample='collection-2')

        def collection_atomic_upsert_test(worker):
            # This method run on separate thread therefore it requires to create a new client and
            # to login it for each call.
            client = Client()
            client.login(username=self.username, password=self.password)
            return client.put(
                reverse('collection-detail', args=[sample['name']]),
                data=sample.get_json('put'),
                content_type='application/json'
            )

        # We call the PUT collection several times in parallel with the same data to make sure
        # that we don't have any race condition.
        responses, errors = self.run_parallel(workers, collection_atomic_upsert_test)

        for worker, response in responses:
            if response.status_code == 201:
                status_201 += 1
            self.assertIn(
                response.status_code, [200, 201],
                msg=f'Unexpected response status code {response.status_code} for worker {worker}'
            )
            self.check_stac_collection(sample.json, response.json())
        self.assertEqual(status_201, 1, msg="Not only one upsert did a create !")

    def test_collection_post_race_condition(self):
        workers = 5
        status_201 = 0
        sample = CollectionFactory().create_sample(sample='collection-2')

        def collection_atomic_post_test(worker):
            # This method run on separate thread therefore it requires to create a new client and
            # to login it for each call.
            client = Client()
            client.login(username=self.username, password=self.password)
            return client.post(
                reverse('collections-list'),
                data=sample.get_json('post'),
                content_type='application/json'
            )

        # We call the PUT collection several times in parallel with the same data to make sure
        # that we don't have any race condition.
        responses, errors = self.run_parallel(workers, collection_atomic_post_test)

        for worker, response in responses:
            self.assertIn(response.status_code, [201, 400])
            if response.status_code == 201:
                self.check_stac_collection(sample.json, response.json())
                status_201 += 1
            else:
                self.assertIn('id', response.json()['description'].keys())
                self.assertIn('This field must be unique.', response.json()['description']['id'])
        self.assertEqual(status_201, 1, msg="Not only one POST was successfull")


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
