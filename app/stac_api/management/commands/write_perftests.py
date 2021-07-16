import logging
import time
from statistics import mean

import requests

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand

from stac_api.utils import CommandHandler
from stac_api.validators import MEDIA_TYPES_BY_TYPE

logger = logging.getLogger(__name__)

GEOMETRIES = {
    'switzerland-west':
        GEOSGeometry(
            'SRID=4326;POLYGON(('
            '5.710217406117146 47.84846875331844,'
            '7.940442015492146 47.84846875331844,'
            '7.940442015492146 45.773562697134,'
            '5.710217406117146 45.773562697134,'
            '5.710217406117146 47.84846875331844))'
        ).json,
    'switzerland-east':
        GEOSGeometry(
            'SRID=4326;POLYGON(('
            '8.094250609242145 47.84846875331844,'
            '10.708996702992145 47.84846875331844,'
            '10.708996702992145 45.773562697134,'
            '8.094250609242145 45.773562697134,'
            '8.094250609242145 47.84846875331844))'
        ).json,
    'switzerland-north':
        GEOSGeometry(
            'SRID=4326;POLYGON(('
            '5.798108031117146 47.84846875331844,'
            '10.708996702992145 47.84846875331844,'
            '10.708996702992145 46.89614858846383,'
            '5.798108031117146 46.89614858846383,'
            '5.798108031117146 47.84846875331844))'
        ).json,
    'switzerland-south':
        GEOSGeometry(
            'SRID=4326;POLYGON(('
            '5.798108031117146 46.89614858846383,'
            '10.708996702992145 46.89614858846383,'
            '10.708996702992145 45.67385578908906,'
            '5.798108031117146 45.67385578908906,'
            '5.798108031117146 46.89614858846383))'
        ).json,
}


class Handler(CommandHandler):

    def clean(self):
        self.print("Starting cleaning %d %s...", self.options['n'], self.options['object_type'])
        headers = self.get_headers()
        auth = self.get_auth()
        deleted = 0
        for i in range(self.options['n']):
            name = self.get_name(i)
            url = self.get_url(name)
            response = requests.delete(url, headers=headers, auth=auth)
            if response.status_code == 200:
                deleted += 1
        self.print_success('%d object deleted', deleted)

    def start(self):
        self.print(
            "Starting write performance tests on %d %s...",
            self.options['n'],
            self.options['object_type']
        )
        headers = self.get_headers()
        auth = self.get_auth()
        create_durations = []
        update_durations = []
        delete_durations = []
        for i in range(self.options['n']):
            # Create test
            data = self.get_data(i)
            name = data['id']
            url = self.get_url(name)
            self.print('Create: PUT %s', url)
            start = time.monotonic()
            response = requests.put(url, json=data, headers=headers, auth=auth)
            duration = time.monotonic() - start
            self.check_response('PUT', url, data, response, 201)
            create_durations.append(duration)

            # update test
            updated_data = self.get_data(i + 1, name=name, init_data=data)
            self.print('Update: PUT %s', url)
            start = time.monotonic()
            response = requests.put(url, json=updated_data, headers=headers, auth=auth)
            duration = time.monotonic() - start
            self.check_response('PUT', url, updated_data, response, 200)
            update_durations.append(duration)

            # delete test
            self.print('Delete: DEL %s', url)
            start = time.monotonic()
            response = requests.delete(url, headers=headers, auth=auth)
            duration = time.monotonic() - start
            self.check_response('DEL', url, None, response, 200)
            delete_durations.append(duration)

        self.print_success('CREATES:')
        self.print_success('    min: %.3fs', min(create_durations))
        self.print_success('    max: %.3fs', max(create_durations))
        self.print_success('    average: %.3fs', mean(create_durations))
        self.print_success('UPDATES:')
        self.print_success('    min: %.3fs', min(update_durations))
        self.print_success('    max: %.3fs', max(update_durations))
        self.print_success('    average: %.3fs', mean(update_durations))
        self.print_success('DELETES:')
        self.print_success('    min: %.3fs', min(delete_durations))
        self.print_success('    max: %.3fs', max(delete_durations))
        self.print_success('    average: %.3fs', mean(delete_durations))
        self.print_success('Done')

    def get_auth(self):
        if 'auth' in self.options:
            return (*self.options['auth'].split(':', maxsplit=1),)
        return None

    def get_headers(self):
        headers = {}
        if 'key' in self.options:
            headers['Authorization'] = f'Token {self.options["key"]}'
        return headers

    def check_response(self, method, url, data, response, expected_code):
        if response.status_code is not expected_code:
            self.print_error(
                'Request %s %s %s failed: %s/%s',
                method,
                url,
                data if data is not None else '',
                response.status_code,
                response.text
            )
            raise RuntimeError()

    def get_url(self, name):
        base = f'{self.options["url"]}/api/stac/v0.9/collections/{self.options["collection"]}/items'
        if self.options['object_type'] == 'items':
            return f'{base}/{name}'
        # else assets
        return f'{base}/{self.options["item"]}/assets/{name}'

    def get_name(self, i):
        if self.options['object_type'] == 'items':
            return f'perftest-write-item-{i}'
        return f'perftest-write-asset-{i}'

    def get_data(self, i, name=None, init_data=None):
        if self.options['object_type'] == 'items':
            return self.get_data_item(i, name=name)
        # else assets
        if init_data:
            return self.get_data_asset(i, name=name, media_type=init_data['type'])
        return self.get_data_asset(i, name=name)

    def get_data_item(self, i, name=None):
        return {
            'id': name if name else self.get_name(i),
            'geometry': self.get_item_geometry(i),
            'properties': self.get_item_properties(i)
        }

    def get_data_asset(self, i, name=None, media_type=None):
        media_types = ['text/plain', 'application/json', 'image/tiff; application=geotiff']
        variants = [None, 'krel', 'komb', 'geoadmin']
        eo_gsds = [None, 1, 0.3, None, 4, 3.2, None]
        proj_epsgs = [None, 2056, None, 4326, 21726]

        if media_type is None:
            media_type = media_types[i % len(media_types)]
        variant = variants[i % len(variants)]
        eo_gsd = eo_gsds[i % len(eo_gsds)]
        proj_epsg = proj_epsgs[i % len(proj_epsgs)]
        ext = MEDIA_TYPES_BY_TYPE[media_type][2][0]
        data = {
            'id': name if name else f'{ self.get_name(i)}.{ext}',
            'type': media_type,
        }
        if variant is not None:
            data['geoadmin:variant'] = variant
        if eo_gsd is not None:
            data['eo:gsd'] = eo_gsd
        if proj_epsg is not None:
            data['proj:epsg'] = proj_epsg

        return data

    def get_item_geometry(self, i):
        geometry_names = [
            'switzerland-west', 'switzerland-east', 'switzerland-north', 'switzerland-south'
        ]
        return GEOMETRIES[geometry_names[i % len(geometry_names)]]

    def get_item_properties(self, i):
        properties = [
            {
                'datetime': '2019-10-28T13:05:10Z'
            },
            {
                'datetime': '2020-10-28T13:05:10Z'
            },
            {
                'datetime': '2021-10-28T13:05:10Z'
            },
            {
                'start_datetime': '2019-10-28T13:05:10Z',
                'end_datetime': '2020-10-28T13:05:10Z',
            },
            {
                'start_datetime': '2016-10-28T13:05:10Z',
                'end_datetime': '2027-10-28T13:05:10Z',
            },
            {
                'start_datetime': '2015-10-28T13:05:10Z',
                'end_datetime': '2021-10-28T13:05:10Z',
            },
        ]
        return properties[i % len(properties)]


class Command(BaseCommand):
    help = """Run write performance tests

    The following three steps are consecutively runned:
    1. create n (items | assets)
    2. update n (items | assets)
    3. delete n (items | assets)
    """

    def add_arguments(self, parser):
        parser.add_argument(
            'object_type',
            type=str,
            choices=['items', 'assets'],
            help='Define which object type to create/update/deletes',
        )

        parser.add_argument(
            '--clean',
            action='store_true',
            help='Clean all object created by the scripts. Usefull if the script failed.'
        )

        parser.add_argument(
            '-n', type=int, default=50, help="Number of object to create/update/delete"
        )

        parser.add_argument(
            '--url', type=str, default='http://localhost:8000', help="Url to run the test against"
        )

        parser.add_argument('--key', type=str, help='Token used for authentication')
        parser.add_argument('--auth', type=str, help='Basic authentication in form user:pass')

        parser.add_argument(
            '--collection',
            type=str,
            default='perftest-collection-1',
            help="Collection on which to run the tests."
        )

        parser.add_argument(
            '--item',
            type=str,
            default='perftest-item-1',
            help="Item on which to run the tests, only valid for 'assets' object_type."
        )

    def handle(self, *args, **options):
        try:
            if options['clean']:
                Handler(self, options).clean()
            else:
                Handler(self, options).start()
        except RuntimeError:
            pass
