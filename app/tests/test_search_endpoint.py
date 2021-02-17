import logging
from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.test import Client

from stac_api.utils import isoformat
from stac_api.utils import utc_aware

from tests.base_test import StacBaseTestCase
from tests.data_factory import Factory
from tests.utils import client_login

logger = logging.getLogger(__name__)

STAC_BASE_V = settings.STAC_BASE_V


class SearchEndpointTestCaseOne(StacBaseTestCase):

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
        cls.now = utc_aware(datetime.utcnow())
        cls.yesterday = cls.now - timedelta(days=1)

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        client_login(self.client)
        self.path = f'/{STAC_BASE_V}/search'

    def test_query(self):
        # get match
        title = "My item 1"
        query = '{"title":{"eq":"%s"}}' % title
        response = self.client.get(f"/{STAC_BASE_V}/search" f"?query={query}&limit=100")
        self.assertStatusCode(200, response)
        json_data_get = response.json()
        self.assertEqual(json_data_get['features'][0]['properties']['title'], title)
        self.assertEqual(len(json_data_get['features']), 1)

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
        self.assertEqual(len(json_data_post['features']), 1)

        # compare get and post
        self.assertEqual(
            json_data_get['features'][0]['properties']['title'],
            json_data_post['features'][0]['properties']['title']
        )

    def test_query_non_allowed_parameters(self):
        # get match
        query = '{"created": {"lte": "9999-12-31T09:07:39.399892Z"}}'
        wrong_query_parameter = "cherry"
        response = self.client.get(
            f"/{STAC_BASE_V}/search"
            f"?{wrong_query_parameter}={query}&limit=1"
        )
        self.assertStatusCode(400, response)
        json_data_get = response.json()
        self.assertIn(
            wrong_query_parameter,
            str(json_data_get['description']),
            msg=f"Wrong query parameter {wrong_query_parameter} not found in error message"
        )
        # self.assertEqual(len(json_data_get['features']), 1)

        # post match
        payload = f"""
        {{"{wrong_query_parameter}":
            {{"created":
                {{"lte":"9999-12-31T09:07:39.399892Z"}}
            }},
            "limit": 1
        }}
        """
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(400, response)
        json_data_post = response.json()
        self.assertIn(
            wrong_query_parameter,
            str(json_data_post['description']),
            msg=f"Wrong query parameter {wrong_query_parameter} not found in error message"
        )

    def test_query_multiple_non_allowed_parameters(self):
        # get match
        query = '{"created": {"lte": "9999-12-31T09:07:39.399892Z"}}'
        wrong_query_parameter1 = "cherry"
        wrong_query_parameter2 = "no_limits"
        response = self.client.get(
            f"/{STAC_BASE_V}/search"
            f"?{wrong_query_parameter1}={query}&{wrong_query_parameter2}=1"
        )
        self.assertStatusCode(400, response)
        json_data_get = response.json()
        for wrong_par in [wrong_query_parameter1, wrong_query_parameter2]:
            self.assertIn(
                wrong_par,
                str(json_data_get['description']),
                msg=f"Wrong query parameter {wrong_par} not found in error message"
            )

        # post match
        payload = f"""
        {{"{wrong_query_parameter1}":
            {{"created":
                {{"lte":"9999-12-31T09:07:39.399892Z"}}
            }},
            "{wrong_query_parameter2}": 1
        }}
        """
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(400, response)
        json_data_post = response.json()
        for wrong_par in [wrong_query_parameter1, wrong_query_parameter2]:
            self.assertIn(
                wrong_par,
                str(json_data_post['description']),
                msg=f"Wrong query parameter {wrong_par} not found in error message"
            )

    def test_query_created(self):
        # get match
        query = '{"created": {"lte": "9999-12-31T09:07:39.399892Z"}}'
        response = self.client.get(f"/{STAC_BASE_V}/search" f"?query={query}&limit=1")
        self.assertStatusCode(200, response)
        json_data_get = response.json()
        self.assertEqual(len(json_data_get['features']), 1)

        # post match
        payload = """
        {"query":
            {"created":
                {"lte":"9999-12-31T09:07:39.399892Z"}
            },
            "limit": 1
        }
        """
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data_post = response.json()
        self.assertEqual(len(json_data_post['features']), 1)
        # compare get and post
        self.assertEqual(
            json_data_get['features'][0]['properties']['created'],
            json_data_post['features'][0]['properties']['created'],
            msg="GET and POST responses do not match when filtering for date created"
        )

    def test_query_updated(self):
        # get match
        query = '{"updated": {"lte": "9999-12-31T09:07:39.399892Z"}}'
        response = self.client.get(f"/{STAC_BASE_V}/search" f"?query={query}&limit=1")
        self.assertStatusCode(200, response)
        json_data_get = response.json()
        self.assertEqual(len(json_data_get['features']), 1)

        # post match
        payload = """
        {"query":
            {"updated":
                {"lte":"9999-12-31T09:07:39.399892Z"}
            },
            "limit": 1
        }
        """
        response = self.client.post(self.path, data=payload, content_type="application/json")
        self.assertStatusCode(200, response)
        json_data_post = response.json()
        self.assertEqual(len(json_data_post['features']), 1)
        # compare get and post
        self.assertEqual(
            json_data_get['features'][0]['properties']['updated'],
            json_data_post['features'][0]['properties']['updated'],
            msg="GET and POST responses do not match when filtering for date updated"
        )

    def test_query_data_in(self):
        payload = """
        {"query":
            {"title":
                {"in":["My item 1","My item 2"]}
            }
        }
        """
        response = self.client.post(self.path, data=payload, content_type="application/json")
        json_data = response.json()
        list_expected_items = ['item-1', 'item-2']
        self.assertIn(json_data['features'][0]['id'], list_expected_items)
        self.assertIn(json_data['features'][1]['id'], list_expected_items)

    def test_post_pagination(self):
        data = """
        {"query":
             {"title":
                {"startsWith":"My item"}
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

    def test_post_intersects_valid(self):
        data = """
        { "intersects":
            { "type": "POINT",
              "coordinates": [6, 47]
            }
        }
        """
        response = self.client.post(f"{self.path}", data=data, content_type="application/json")
        json_data = response.json()
        self.assertEqual(json_data['features'][0]['id'], 'item-3')

    def test_post_intersects_invalid(self):
        data = """
        { "intersects":
            { "type": "POINT",
              "coordinates": [6, 47, "kaputt"]
            }
        }
        """
        response = self.client.post(f"{self.path}", data=data, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_collections_get(self):
        # match
        response = self.client.get(f"/{STAC_BASE_V}/search" f"?collections=collection-1,har")
        self.assertStatusCode(200, response)
        json_data = response.json()
        for feature in json_data['features']:
            self.assertEqual(feature['collection'], 'collection-1')
        # no match
        response = self.client.get(f"/{STAC_BASE_V}/search" f"?collections=collection-11,har")
        self.assertStatusCode(200, response)
        json_data = response.json()
        self.assertEqual(len(json_data['features']), 0)

    def test_collections_post_valid(self):
        payload = """
           { "collections": [
              "collection-1"
               ]
           }
           """
        response = self.client.post(f"{self.path}", data=payload, content_type="application/json")
        json_data = response.json()
        for feature in json_data['features']:
            self.assertEqual(feature['collection'], 'collection-1')

    def test_collections_post_invalid(self):
        payload = """
           { "collections": [
              "collection-1",
              9999
               ]
           }
           """
        response = self.client.post(f"{self.path}", data=payload, content_type="application/json")
        self.assertStatusCode(400, response)


class SearchEndpointTestCaseTwo(StacBaseTestCase):

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
        cls.now = utc_aware(datetime.utcnow())
        cls.yesterday = cls.now - timedelta(days=1)

    def setUp(self):  # pylint: disable=invalid-name
        self.client = Client()
        client_login(self.client)
        self.path = f'/{STAC_BASE_V}/search'

    def test_ids_get_valid(self):
        response = self.client.get(f"/{STAC_BASE_V}/search" f"?ids=item-1,item-2")
        self.assertStatusCode(200, response)
        json_data = response.json()
        list_expected_items = ['item-1', 'item-2']
        self.assertIn(json_data['features'][0]['id'], list_expected_items)
        self.assertIn(json_data['features'][1]['id'], list_expected_items)

    def test_ids_post_valid(self):
        payload = """
                  { "ids": [
                    "item-1",
                    "item-2"
                      ]
                  }
        """
        response = self.client.post(f"{self.path}", data=payload, content_type="application/json")
        json_data = response.json()
        list_expected_items = ['item-1', 'item-2']
        self.assertIn(json_data['features'][0]['id'], list_expected_items)
        self.assertIn(json_data['features'][1]['id'], list_expected_items)

    def test_ids_post_invalid(self):
        payload = """
                  { "ids": [
                    "item-1",
                    "item-2",
                    1
                      ]
                  }
        """
        response = self.client.post(f"{self.path}", data=payload, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_ids_first_and_only_prio(self):
        response = self.client.get(
            f"/{STAC_BASE_V}/search"
            f"?ids=item-1,item-2&collections=not_exist"
        )
        self.assertStatusCode(200, response)
        json_data = response.json()
        list_expected_items = ['item-1', 'item-2']
        self.assertIn(json_data['features'][0]['id'], list_expected_items)
        self.assertIn(json_data['features'][1]['id'], list_expected_items)

    def test_bbox_valid(self):
        payload = """
        { "bbox": [
            6,
            47,
            6.5,
            47.5
            ]
        }
        """
        response = self.client.post(f"{self.path}", data=payload, content_type="application/json")
        json_data_post = response.json()
        list_expected_items = ['item-1', 'item-2']
        self.assertIn(json_data_post['features'][0]['id'], list_expected_items)
        self.assertIn(json_data_post['features'][1]['id'], list_expected_items)

        response = self.client.get(f"/{STAC_BASE_V}/search" f"?bbox=6,47,6.5,47.5&limit=100")
        json_data_get = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(json_data_get['features'][0]['id'], json_data_post['features'][0]['id'])

    def test_bbox_as_point(self):
        # bbox as a point
        payload = """
        { "bbox": [
            6.1,
            47.1,
            6.1,
            47.1
            ],
          "limit": 100
        }
        """
        response = self.client.post(f"{self.path}", data=payload, content_type="application/json")
        json_data_post = response.json()
        list_expected_items = ['item-3', 'item-4', 'item-6']
        self.assertIn(json_data_post['features'][0]['id'], list_expected_items)
        self.assertIn(json_data_post['features'][1]['id'], list_expected_items)
        self.assertIn(json_data_post['features'][2]['id'], list_expected_items)

        response = self.client.get(f"/{STAC_BASE_V}/search" f"?bbox=6.1,47.1,6.1,47.1&limit=100")
        json_data_get = response.json()
        self.assertStatusCode(200, response)

        self.assertIn(json_data_get['features'][0]['id'], list_expected_items)
        self.assertIn(json_data_get['features'][1]['id'], list_expected_items)
        self.assertIn(json_data_get['features'][2]['id'], list_expected_items)
        self.assertEqual(json_data_get['features'][0]['id'], json_data_post['features'][0]['id'])

    def test_bbox_post_invalid(self):
        payload = """
        { "bbox": [
            6,
            47,
            6.5,
            47.5,
            5.5
            ]
        }
        """
        response = self.client.post(f"{self.path}", data=payload, content_type="application/json")
        self.assertStatusCode(400, response)

    def test_bbox_get_invalid(self):
        response = self.client.get(f"/{STAC_BASE_V}/search" f"?bbox=6,47,6.5,47.5,5.5")
        self.assertStatusCode(400, response)

    def test_datetime_open_end_range_query_get(self):
        response = self.client.get(
            f"/{STAC_BASE_V}/search"
            f"?datetime={isoformat(self.yesterday)}/..&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(0, len(json_data['features']))

    def test_datetime_open_start_range_query(self):
        response = self.client.get(
            f"/{STAC_BASE_V}/search"
            f"?datetime=../{isoformat(self.yesterday)}&limit=100"
        )
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(8, len(json_data['features']), msg="More than two item found")
        self.assertEqual('item-1', json_data['features'][0]['id'])
        self.assertEqual('item-8', json_data['features'][7]['id'])

        payload = """
        { "datetime": "../%s"
        }
        """ % isoformat(self.yesterday)
        json_data = response.json()
        self.assertStatusCode(200, response)
        self.assertEqual(8, len(json_data['features']), msg="More than two item found")
        self.assertEqual('item-1', json_data['features'][0]['id'])
        self.assertEqual('item-8', json_data['features'][7]['id'])

    def test_datetime_invalid_range_query_get(self):
        response = self.client.get(f"/{STAC_BASE_V}/search" f"?datetime=../..&limit=100")
        self.assertStatusCode(400, response)

    def test_datetime_exact_query_get(self):
        response = self.client.get(
            f"/{STAC_BASE_V}/search"
            f"?datetime=2020-10-28T13:05:10Z&limit=100"
        )
        json_data = response.json()
        self.assertEqual(7, len(json_data['features']), msg="Seven items Found")
        self.assertEqual('item-1', json_data['features'][0]['id'])
        self.assertEqual('item-8', json_data['features'][6]['id'])
        self.assertStatusCode(200, response)

    def test_datetime_invalid_format_query_get(self):
        response = self.client.get(f"/{STAC_BASE_V}/search?datetime=NotADate&limit=100")
        self.assertStatusCode(400, response)
