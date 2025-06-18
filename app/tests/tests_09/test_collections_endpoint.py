import logging
from datetime import UTC
from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from stac_api.models.collection import Collection
from stac_api.models.collection import CollectionLink
from stac_api.models.general import Provider

from tests.tests_09.base_test import STAC_BASE_V
from tests.tests_09.base_test import StacBaseTestCase
from tests.tests_09.base_test import StacBaseTransactionTestCase
from tests.tests_09.data_factory import CollectionFactory
from tests.tests_09.data_factory import Factory
from tests.tests_09.utils import reverse_version
from tests.utils import client_login
from tests.utils import disableLogger

logger = logging.getLogger(__name__)


class CollectionsEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.factory = CollectionFactory()
        self.collection_1 = self.factory.create_sample(
            sample='collection-1', name='collection-1', db_create=True
        )
        self.collection_2 = self.factory.create_sample(
            sample='collection-2', name='collection-2', db_create=True
        )
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_collections_endpoint(self):
        # create a third collection with an ascendent name to make sure that collections
        # ordering is working
        collection_3 = self.factory.create_sample(
            sample='collection-2', name='collection-0', db_create=True
        )
        response = self.client.get(f"/{STAC_BASE_V}/collections")
        response_json = response.json()
        self.assertStatusCode(200, response)

        # Check that the output is sorted by id
        collection_ids = [collection['id'] for collection in response_json['collections']]
        self.assertListEqual(
            collection_ids, sorted(collection_ids), msg="Collections are not sorted by ID"
        )

        collection_samples = sorted([self.collection_1, self.collection_2, collection_3],
                                    key=lambda collection: collection['name'])
        for i, collection in enumerate(collection_samples):
            self.check_stac_collection(collection.json, response_json['collections'][i])

    def test_single_collection_endpoint(self):
        collection_name = self.collection_1.attributes['name']
        response = self.client.get(f"/{STAC_BASE_V}/collections/{collection_name}")
        response_json = response.json()
        self.assertStatusCode(200, response)
        # The ETag change between each test call due to the created, updated time that are in the
        # hash computation of the ETag
        self.assertEtagHeader(None, response)

        self.check_stac_collection(self.collection_1.json, response_json)


class CollectionsUnImplementedEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        client_login(self.client)
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample()
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_collections_post_unimplemented(self):
        response = self.client.post(
            f"/{STAC_BASE_V}/collections",
            data=self.collection.get_json('post'),
            content_type='application/json'
        )
        self.assertStatusCode(405, response)


class CollectionsCreateEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        client_login(self.client)
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample()
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_collection_upsert_create(self):
        sample = self.factory.create_collection_sample(sample='collection-2')

        # the dataset to update does not exist yet
        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{sample['name']}",
            data=sample.get_json('put'),
            content_type='application/json'
        )
        self.assertStatusCode(201, response)

        self.check_stac_collection(sample.json, response.json())

    def test_invalid_collections_create(self):
        # the dataset already exists in the database
        collection = self.factory.create_collection_sample(sample='collection-invalid')

        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{collection['name']}",
            data=collection.get_json('put'),
            content_type='application/json'
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'license': ['Not a valid string.']},
                         response.json()['description'],
                         msg='Unexpected error message')

    def test_collections_min_mandatory_create(self):
        # a post with the absolute valid minimum
        collection = self.factory.create_collection_sample(required_only=True)

        path = f"/{STAC_BASE_V}/collections/{collection['name']}"
        response = self.client.put(
            path, data=collection.get_json('put'), content_type='application/json'
        )
        response_json = response.json()
        logger.debug(response_json)
        self.assertStatusCode(201, response)
        self.assertLocationHeader(f'{path}', response)
        self.assertNotIn('title', response_json.keys())  # key does not exist
        self.assertNotIn('providers', response_json.keys())  # key does not exist
        self.check_stac_collection(collection.json, response_json)

    def test_collections_less_than_mandatory_create(self):
        # a post with the absolute valid minimum
        collection = self.factory.create_collection_sample(
            sample='collection-missing-mandatory-fields'
        )

        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{collection['name']}",
            data=collection.get_json('put'),
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

    def test_collections_create_unpublished(self):
        published_collection = self.factory.create_collection_sample(db_create=True)
        published_items = self.factory.create_item_samples(
            2, collection=published_collection.model, name=['item-1-1', 'item-1-2'], db_create=True
        )

        collection_sample = self.factory.create_collection_sample(published=False)

        path = f"/{STAC_BASE_V}/collections/{collection_sample['name']}"
        response = self.client.put(
            path, data=collection_sample.get_json('put'), content_type='application/json'
        )
        self.assertStatusCode(201, response)
        self.assertLocationHeader(f'{path}', response)
        self.assertNotIn(
            'published', response.json(), msg="'published' flag should not be seen in answer"
        )
        collection = Collection.objects.get(name=collection_sample['name'])
        self.assertFalse(
            collection.published, msg='Collection marked as published when it shouldn\'t'
        )

        # verify that the collection is not found in the collection list
        response = self.client.get(f"/{STAC_BASE_V}/collections")
        self.assertStatusCode(200, response)
        self.assertEqual(
            len(response.json()['collections']),
            1,
            msg="The un published collection is part of the collection list"
        )
        self.assertEqual(response.json()['collections'][0]['id'], published_collection['name'])

        # add some items to the collection
        items = self.factory.create_item_samples(
            2, collection=collection, name=['item-2-1', 'item-2-2'], db_create=True
        )

        # Check that those items are not found in the search endpoint
        response = self.client.get(f'/{STAC_BASE_V}/search')
        self.assertStatusCode(200, response)
        self.assertEqual(
            len(response.json()['features']),
            2,
            msg="Too many items found, probably the unpublished are also returned"
        )
        for i, item in enumerate(response.json()['features']):
            self.assertEqual(item['id'], published_items[i]['name'])

        # Publish the collection
        response = self.client.patch(
            f"/{STAC_BASE_V}/collections/{collection.name}",
            data={'published': True},
            content_type='application/json'
        )
        self.assertStatusCode(200, response)

        # verify that now the collection can be seen
        response = self.client.get(f"/{STAC_BASE_V}/collections")
        self.assertStatusCode(200, response)
        self.assertEqual(len(response.json()['collections']), 2, msg="No enough collections found")
        self.assertEqual(response.json()['collections'][0]['id'], published_collection.json['id'])
        self.assertEqual(response.json()['collections'][1]['id'], collection.name)

        # Check that the items are found in the search endpoint
        response = self.client.get(f'/{STAC_BASE_V}/search')
        self.assertStatusCode(200, response)
        self.assertEqual(len(response.json()['features']), 4, msg="Not all published items found")

    def test_collection_atomic_upsert_create_500(self):
        sample = self.factory.create_collection_sample(sample='collection-2')

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
        response = self.client.get(reverse_version('collection-detail', args=[sample['name']]))
        self.assertStatusCode(404, response)


class CollectionsUpdateEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        client_login(self.client)
        self.collection_factory = CollectionFactory()
        self.collection = self.collection_factory.create_sample(db_create=True)
        self.maxDiff = None  # pylint: disable=invalid-name

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
            name=self.collection['name'], sample='collection-2', created=datetime.now(UTC)
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
        # Renaming is no longer allowed, due to this the test has been adapted
        sample = self.collection_factory.create_sample(
            name='new-collection-name', sample='collection-2'
        )

        # test if renaming does not work
        self.assertNotEqual(self.collection['name'], sample['name'])
        response = self.client.put(
            f"/{STAC_BASE_V}/collections/{self.collection['name']}",
            data=sample.get_json('put'),
            content_type='application/json'
        )
        self.assertStatusCode(400, response)
        self.assertEqual({'id': 'Renaming is not allowed'},
                         response.json()['description'],
                         msg='Unexpected error message')

        # check if id has not changed
        response = self.client.get(f"/{STAC_BASE_V}/collections/{sample['name']}")
        self.assertStatusCode(404, response)

        # the old collection should still exist
        response = self.client.get(f"/{STAC_BASE_V}/collections/{self.collection['name']}")
        self.assertStatusCode(200, response)

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
        payload_json = {'license': 'open-source', 'created': datetime.now(UTC)}
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
        response = self.client.get(reverse_version('collection-detail', args=[sample['name']]))
        self.assertStatusCode(200, response)
        self.check_stac_collection(self.collection.json, response.json())


class CollectionsDeleteEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        client_login(self.client)
        self.factory = Factory()
        self.collection = self.factory.create_collection_sample(db_create=True)
        self.item = self.factory.create_item_sample(self.collection.model, db_create=True)
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_authorized_collection_delete(self):

        path = reverse_version('collection-detail', args=[self.collection["name"]])
        response = self.client.delete(path)

        self.assertStatusCode(400, response)
        self.assertEqual(
            response.json()['description'], ['Deleting Collection with items not allowed']
        )

        # delete first the item
        item_path = reverse_version(
            'item-detail', args=[self.collection["name"], self.item['name']]
        )
        response = self.client.delete(item_path)
        self.assertStatusCode(200, response)

        # try the collection delete again
        response = self.client.delete(path)
        self.assertStatusCode(200, response)

        # Check that the object doesn't exists anymore
        self.assertFalse(
            CollectionLink.objects.filter(collection__name=self.collection["name"]).exists(),
            msg="Deleted collection link still in DB"
        )
        self.assertFalse(
            Provider.objects.filter(collection__name=self.collection["name"]).exists(),
            msg="Deleted provider still in DB"
        )
        self.assertFalse(
            Collection.objects.filter(name=self.collection["name"]).exists(),
            msg="Deleted collection still in DB"
        )


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
            # This method runs on separate thread therefore it requires to create a new client and
            # to login it for each call.
            client = Client()
            client.login(username=self.username, password=self.password)
            return client.put(
                reverse_version('collection-detail', args=[sample['name']]),
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


class CollectionsUnauthorizeEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.collection_factory = CollectionFactory()
        self.collection = self.collection_factory.create_sample().model
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_unauthorized_collection_put_patch(self):
        # make sure POST fails for anonymous user:
        # a post with the absolute valid minimum
        sample = self.collection_factory.create_sample(sample='collection-2')

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
