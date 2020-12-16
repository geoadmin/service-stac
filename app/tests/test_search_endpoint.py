import logging
import sys

from django.conf import settings
from django.test import Client

from tests.base_test import StacBaseTestCase
from tests.data_factory import Factory
from tests.utils import client_login

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)


API_BASE = settings.API_BASE


class SearchEndpointTestCase(StacBaseTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory()
        cls.collection = cls.factory.create_collection_sample().model
        cls.items = cls.factory.create_item_samples(
            [
                'item-1',
                'item-2',
                'item-switzerland',
                'item-switzerland-west',
                'item-switzerland-east',
                'item-switzerland-north',
                'item-switzerland-south',
                'item-paris'
            ],
            cls.collection,
            db_create=True,
        )

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        client_login(self.client)
        self.path = f'/{API_BASE}/search'

    def test_query(self):
        # get match
        title = "My item 1"
        query = '{"title":{"eq":"%s"}}' % title
        response = self.client.get(
            f"/{API_BASE}/search"
            f"?query={query}&limit=100")
        self.assertStatusCode(200, response)
        json_data_get = response.json()
        self.assertEqual(json_data_get['features'][0]['properties']['title'], title)

        # post match
        payload = """
        {"query":
            {"title":
                {"eq":"My item 1"}
            }
        }
        """
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data_post = response.json()
        self.assertEqual(json_data_post['features'][0]['properties']['title'], title)

        # compare get and post
        self.assertEqual(len(json_data_post['features']), len(json_data_get['features']))


    def test_query_data_in(self):
        payload = """
        {"query":
            {"datetime":
                {"in":["2020-10-28T13:05:10Z","2525-10-19T00:00:00Z"]}
            }
        }
        """
        response = self.client.post(self.path, data=payload, content_type="application/json")
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 2)


    def test_post_pagination(self):
        data = """
        {"query":
            {"datetime":
                {"lt":"2525-01-02T00:00:00Z"}
            },
         "limit": 1
        }
        """
        response = self.client.post(self.path, data=data, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data = response.json()
        links = json_data['links']
        # get the curser value of next
        for link in links:
            if link['rel'] == 'next':
                cursor = link['href'].split('?')[1]
        item_id1 = json_data['features'][0]['id']

        # pagination
        response = self.client.get(f"{self.path}?{cursor}")
        self.assertStatusCode(200, response)
        json_data = response.json()
        item_id2 = json_data['features'][0]['id']
        self.assertNotEqual(item_id1, item_id2)


    def test_post_intersects(self):
        data = """
        { "intersects":
            { "type": "POINT",
              "coordinates": [6, 47]
            }
        }
        """
        response = self.client.post(f"{self.path}", data=data, content_type="application/json")
        json_data = response.json()
        self.assertGreater(len(json_data['features']), 0)

    def test_collections(self):
        # match
        response = self.client.get(
            f"/{API_BASE}/search"
            f"?collections=collection-1,har")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertGreater(len(json_data['features']), 0)
        # no match
        response = self.client.get(
            f"/{API_BASE}/search"
            f"?collections=collection-11,har")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 0)

    def test_ids(self):
        response = self.client.get(
            f"/{API_BASE}/search"
            f"?ids=item-1,item-2")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 2)

    def test_ids_first_and_only_prio(self):
        response = self.client.get(
            f"/{API_BASE}/search"
            f"?ids=item-1,item-2&collections=not_exist")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 2)
