import logging
from datetime import datetime
from pprint import pformat

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

from rest_framework.test import APIRequestFactory

from stac_api.serializers import CollectionSerializer
from stac_api.utils import fromisoformat
from stac_api.utils import utc_aware

import tests.database as db
from tests.base_test import StacBaseTestCase
from tests.utils import get_sample_data
from tests.utils import mock_request_from_response

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


class CollectionsEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.factory = APIRequestFactory()
        self.collections, self.items, self.assets = db.create_dummy_db_content(4, 4, 4)
        self.maxDiff = None  # pylint: disable=invalid-name
        self.sample_collections = get_sample_data('collections')
        self.username = 'SherlockHolmes'
        self.password = '221B_BakerStreet'
        self.superuser = get_user_model().objects.create_superuser(
            self.username, 'test_e_mail1234@some_fantasy_domainname.com', self.password
        )

    def test_collections_endpoint(self):
        response = self.client.get(f"/{API_BASE}/collections")
        response_json = response.json()
        self.assertStatusCode(200, response)

        # mock the request for creations of links
        request = mock_request_from_response(self.factory, response)

        # transate to Python native:
        serializer = CollectionSerializer(self.collections, many=True, context={'request': request})
        logger.debug('Serialized data:\n%s', pformat(serializer.data))
        logger.debug('Response:\n%s', pformat(response_json))
        self.assertListEqual(
            serializer.data[:2],
            response_json['collections'],
            msg="Returned data does not match expected data"
        )
        self.assertListEqual(['rel', 'href'], list(response_json['links'][0].keys()))

    def test_single_collection_endpoint(self):
        collection_name = self.collections[0].name
        response = self.client.get(f"/{API_BASE}/collections/{collection_name}")
        response_json = response.json()
        self.assertStatusCode(200, response)
        # The ETag change between each test call due to the created, updated time that are in the
        # hash computation of the ETag
        self.check_etag(None, response)

        # mock the request for creations of links
        request = mock_request_from_response(self.factory, response)

        # translate to Python native:
        serializer = CollectionSerializer(self.collections, many=True, context={'request': request})
        self.assertDictContainsSubset(
            serializer.data[0], response.data, msg="Returned data does not match expected data"
        )
        # created and updated must exist and be a valid date
        date_fields = ['created', 'updated']
        for date_field in date_fields:
            self.assertTrue(
                fromisoformat(response_json[date_field]),
                msg=f"The field {date_field} has an invalid date"
            )

    def test_collections_limit_query(self):
        response = self.client.get(f"/{API_BASE}/collections?limit=1")
        self.assertStatusCode(200, response)
        self.assertLessEqual(1, len(response.json()['collections']))

        response = self.client.get(f"/{API_BASE}/collections?limit=0")
        self.assertStatusCode(400, response)

        response = self.client.get(f"/{API_BASE}/collections?limit=test")
        self.assertStatusCode(400, response)

        response = self.client.get(f"/{API_BASE}/collections?limit=-1")
        self.assertStatusCode(400, response)

        response = self.client.get(f"/{API_BASE}/collections?limit=1000")
        self.assertStatusCode(400, response)


class CollectionsWriteEndpointTestCase(StacBaseTestCase):

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        self.factory = APIRequestFactory()
        self.collections, self.items, self.assets = db.create_dummy_db_content(4, 4, 4)
        self.maxDiff = None  # pylint: disable=invalid-name
        self.sample_collections = get_sample_data('collections')
        self.username = 'SherlockHolmes'
        self.password = '221B_BakerStreet'
        self.superuser = get_user_model().objects.create_superuser(
            self.username, 'test_e_mail1234@some_fantasy_domainname.com', self.password
        )

    def test_valid_collections_post(self):
        payload_json = self.sample_collections['valid_collection_set_1']

        self.client.login(username=self.username, password=self.password)
        response = self.client.post(
            f"/{API_BASE}/collections", data=payload_json, content_type='application/json'
        )
        response_json = response.json()
        self.assertStatusCode(201, response)

        response = self.client.get(f"/{API_BASE}/collections/{payload_json['id']}")
        response_json = response.json()
        self.assertEqual(response_json['id'], payload_json['id'])

        # the dataset already exists in the database
        self.client.login(username=self.username, password=self.password)
        response = self.client.post(
            f"/{API_BASE}/collections", data=payload_json, content_type='application/json'
        )
        response_json = response.json()
        self.assertStatusCode(400, response)

    def test_collections_post_extra_payload(self):
        payload_json = self.sample_collections['valid_collection_set_1']
        payload_json["crazy:stuff"] = "woooohoooo"

        self.client.login(username=self.username, password=self.password)
        response = self.client.post(
            f"/{API_BASE}/collections", data=payload_json, content_type='application/json'
        )
        self.assertStatusCode(400, response)

    def test_collections_post_read_only_in_payload(self):
        payload_json = self.sample_collections['valid_collection_set_1']
        payload_json["created"] = utc_aware(datetime.utcnow())

        self.client.login(username=self.username, password=self.password)
        response = self.client.post(
            f"/{API_BASE}/collections", data=payload_json, content_type='application/json'
        )
        self.assertStatusCode(400, response)

    def test_invalid_collections_post(self):
        # the dataset already exists in the database
        payload_json = self.sample_collections['invalid_collection_set_1']

        self.client.login(username=self.username, password=self.password)
        response = self.client.post(
            f"/{API_BASE}/collections", data=payload_json, content_type='application/json'
        )
        response_json = response.json()
        self.assertStatusCode(400, response)

    def test_collections_min_mandatory_post(self):
        # a post with the absolute valid minimum
        payload_json = self.sample_collections['valid_min_collection_set_1']

        self.client.login(username=self.username, password=self.password)
        response = self.client.post(
            f"/{API_BASE}/collections", data=payload_json, content_type='application/json'
        )
        response_json = response.json()
        logger.debug(response_json)
        self.assertStatusCode(201, response)
        self.assertNotIn('title', response_json.keys())  # key does not exist
        self.assertNotIn('providers', response_json.keys())  # key does not exist

    def test_collections_less_than_mandatory_post(self):
        # a post with the absolute valid minimum
        payload_json = self.sample_collections['less_than_min_collection_set']

        self.client.login(username=self.username, password=self.password)
        response = self.client.post(
            f"/{API_BASE}/collections", data=payload_json, content_type='application/json'
        )
        response_json = response.json()
        self.assertStatusCode(400, response)

    def test_collections_put(self):
        payload_json = self.sample_collections['valid_collection_set_2']

        # the dataset to update does not exist yet
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(
            f"/{API_BASE}/collections/{payload_json['id']}",
            data=payload_json,
            content_type='application/json'
        )
        response_json = response.json()
        self.assertStatusCode(404, response)

        # POST data
        self.client.post(
            f"/{API_BASE}/collections", data=payload_json, content_type='application/json'
        )

        payload_json['title'] = "The Swallows"
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(
            f"/{API_BASE}/collections/{payload_json['id']}",
            data=payload_json,
            content_type='application/json'
        )
        response_json = response.json()

        self.assertStatusCode(200, response)
        self.assertEqual(response_json['title'], payload_json['title'])
        self.assertIn('providers', response_json.keys())  # optional value, should exist

        # is it persistent?
        response = self.client.get(
            f"/{API_BASE}/collections/{payload_json['id']}",
            data=payload_json,
            content_type='application/json'
        )

        response_json = response.json()

        self.assertStatusCode(200, response)
        self.assertEqual(response_json['title'], payload_json['title'])

    def test_collections_put_extra_payload(self):
        payload_json = self.sample_collections['valid_collection_set_2']
        # POST data first
        self.client.login(username=self.username, password=self.password)
        self.client.post(
            f"/{API_BASE}/collections", data=payload_json, content_type='application/json'
        )

        payload_json['title'] = "The Swallows"
        payload_json["crazy:stuff"] = "woooohoooo"
        response = self.client.put(
            f"/{API_BASE}/collections/{payload_json['id']}",
            data=payload_json,
            content_type='application/json'
        )
        self.assertStatusCode(400, response)

    def test_collections_put_read_only_in_payload(self):
        payload_json = self.sample_collections['valid_collection_set_2']
        # POST data first
        self.client.login(username=self.username, password=self.password)
        self.client.post(
            f"/{API_BASE}/collections", data=payload_json, content_type='application/json'
        )

        payload_json['title'] = "The Swallows"
        payload_json["created"] = utc_aware(datetime.utcnow())
        response = self.client.put(
            f"/{API_BASE}/collections/{payload_json['id']}",
            data=payload_json,
            content_type='application/json'
        )
        self.assertStatusCode(400, response)

    def test_collection_put_change_id(self):
        payload_json = self.sample_collections['valid_collection_set_3']
        # for the start, the id have to be different
        self.assertNotEqual(self.collections[0].name, payload_json['id'])
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(
            f"/{API_BASE}/collections/{self.collections[0].name}",
            data=payload_json,
            content_type='application/json'
        )
        response_json = response.json()
        self.assertStatusCode(200, response)

        # check if id changed
        response = self.client.get(f"/{API_BASE}/collections/{payload_json['id']}")
        self.assertStatusCode(200, response)
        response_json = response.json()
        self.assertEqual(response_json['id'], payload_json['id'])

        # the old collection shouldn't exist any more
        response = self.client.get(f"/{API_BASE}/collections/{self.collections[0].name}")
        response_json = response.json()
        self.assertStatusCode(404, response)

    def test_collection_put_remove_optional_fields(self):
        collection_name = self.collections[1].name  # get a name that is registered in the service
        payload_json = self.sample_collections['valid_min_collection_set_2']
        payload_json['id'] = collection_name  # rename the payload to this name
        # for the start, the collection[1] has to have a title
        self.assertNotEqual('', f'{self.collections[1].title}')
        # for the start, the collection[1] has to have providers
        self.assertNotEqual(self.collections[1].providers, [])
        self.client.login(username=self.username, password=self.password)
        response = self.client.put(
            f"/{API_BASE}/collections/{payload_json['id']}",
            data=payload_json,
            content_type='application/json'
        )
        self.assertStatusCode(200, response)
        response_json = response.json()
        self.assertNotIn('title', response_json.keys())  # key does not exist
        self.assertNotIn('providers', response_json.keys())  # key does not exist

    def test_collection_patch(self):
        collection_name = self.collections[1].name  # get a name that is registered in the service
        payload_json = self.sample_collections['less_than_min_collection_set']
        payload_json['id'] = collection_name  # rename the payload to this name
        # for the start, the collection[1] has to have a different licence than the payload
        self.assertNotEqual(self.collections[1].license, payload_json['license'])
        # for start the payload has no description
        self.assertNotIn('title', payload_json.keys())
        self.client.login(username=self.username, password=self.password)
        response = self.client.patch(
            f"/{API_BASE}/collections/{payload_json['id']}",
            data=payload_json,
            content_type='application/json'
        )
        self.assertStatusCode(200, response)
        response_json = response.json()
        # licence affected by patch
        self.assertEqual(payload_json['license'], response_json['license'])

        # description not affected by patch
        self.assertEqual(self.collections[1].description, response_json['description'])

    def test_collection_patch_extra_payload(self):
        collection_name = self.collections[1].name  # get a name that is registered in the service
        payload_json = self.sample_collections['less_than_min_collection_set']
        payload_json['id'] = collection_name  # rename the payload to this name
        payload_json["crazy:stuff"] = "woooohoooo"
        # for the start, the collection[1] has to have a different licence than the payload
        self.assertNotEqual(self.collections[1].license, payload_json['license'])
        # for start the payload has no description
        self.assertNotIn('title', payload_json.keys())
        self.client.login(username=self.username, password=self.password)
        response = self.client.patch(
            f"/{API_BASE}/collections/{payload_json['id']}",
            data=payload_json,
            content_type='application/json'
        )
        self.assertStatusCode(400, response)

    def test_collection_patch_read_only_in_payload(self):
        collection_name = self.collections[1].name  # get a name that is registered in the service
        payload_json = self.sample_collections['less_than_min_collection_set']
        payload_json['id'] = collection_name  # rename the payload to this name
        payload_json["created"] = utc_aware(datetime.utcnow())
        # for the start, the collection[1] has to have a different licence than the payload
        self.assertNotEqual(self.collections[1].license, payload_json['license'])
        # for start the payload has no description
        self.assertNotIn('title', payload_json.keys())
        self.client.login(username=self.username, password=self.password)
        response = self.client.patch(
            f"/{API_BASE}/collections/{payload_json['id']}",
            data=payload_json,
            content_type='application/json'
        )
        self.assertStatusCode(400, response)

    def test_unauthorized_collection_post_put_patch(self):
        # make sure POST fails for anonymous user:
        # a post with the absolute valid minimum
        payload_json = self.sample_collections['valid_min_collection_set_1']

        response = self.client.post(
            f"/{API_BASE}/collections", data=payload_json, content_type='application/json'
        )
        self.assertEqual(401, response.status_code, msg="Unauthorized post was permitted.")

        # make sure PUT fails for anonymous user:
        payload_json = self.sample_collections['valid_collection_set_3']
        # for the start, the id have to be different
        self.assertNotEqual(self.collections[0].name, payload_json['id'])
        response = self.client.put(
            f"/{API_BASE}/collections/{self.collections[0].name}",
            data=payload_json,
            content_type='application/json'
        )
        self.assertEqual(401, response.status_code, msg="Unauthorized put was permitted.")

        # make sure PATCH fails for anonymous user:
        collection_name = self.collections[1].name  # get a name that is registered in the service
        payload_json = self.sample_collections['less_than_min_collection_set']
        payload_json['id'] = collection_name  # rename the payload to this name
        # for the start, the collection[1] has to have a different licence than the payload
        self.assertNotEqual(self.collections[1].license, payload_json['license'])
        # for start the payload has no description
        self.assertNotIn('title', payload_json.keys())
        response = self.client.patch(
            f"/{API_BASE}/collections/{payload_json['id']}",
            data=payload_json,
            content_type='application/json'
        )
        self.assertEqual(401, response.status_code, msg="Unauthorized patch was permitted.")

    def test_unauthorized_collection_delete(self):
        path = f'/{API_BASE}/collections/{self.collections[0].name}'
        response = self.client.delete(path)
        # Collection delete is not implemented (and currently not foreseen).
        # Status code here is 401, as user is unauthorized for write requests.
        # If logged-in, it should be 405, as DELETE for collections is not
        # implemented.
        self.assertEqual(
            401,
            response.status_code,
            msg="unauthorized and unimplemented "
            "collection delete was permitted."
        )

    def test_authorized_collection_delete(self):
        path = f'/{API_BASE}/collections/{self.collections[0].name}'
        self.client.login(username=self.username, password=self.password)
        response = self.client.delete(path)
        # Collection delete is not implemented (and currently not foreseen), hence
        # the status code should be 405. If it should get implemented in future
        # an unauthorized delete should get a status code of 401 (see test above).
        self.assertEqual(
            405, response.status_code, msg="unimplemented collection delete was permitted."
        )
