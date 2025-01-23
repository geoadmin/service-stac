import json

from django.contrib.gis.geos import GEOSGeometry

from stac_api.models import BBOX_CH
from stac_api.utils import fromisoformat

geometries = {
    'switzerland': GEOSGeometry(BBOX_CH),
    'switzerland-west':
        GEOSGeometry(
            'SRID=4326;POLYGON(('
            '5.710217406117146 47.84846875331844,'
            '7.940442015492146 47.84846875331844,'
            '7.940442015492146 45.773562697134,'
            '5.710217406117146 45.773562697134,'
            '5.710217406117146 47.84846875331844))'
        ),
    'switzerland-east':
        GEOSGeometry(
            'SRID=4326;POLYGON(('
            '8.094250609242145 47.84846875331844,'
            '10.708996702992145 47.84846875331844,'
            '10.708996702992145 45.773562697134,'
            '8.094250609242145 45.773562697134,'
            '8.094250609242145 47.84846875331844))'
        ),
    'switzerland-north':
        GEOSGeometry(
            'SRID=4326;POLYGON(('
            '5.798108031117146 47.84846875331844,'
            '10.708996702992145 47.84846875331844,'
            '10.708996702992145 46.89614858846383,'
            '5.798108031117146 46.89614858846383,'
            '5.798108031117146 47.84846875331844))'
        ),
    'switzerland-south':
        GEOSGeometry(
            'SRID=4326;POLYGON(('
            '5.798108031117146 46.89614858846383,'
            '10.708996702992145 46.89614858846383,'
            '10.708996702992145 45.67385578908906,'
            '5.798108031117146 45.67385578908906,'
            '5.798108031117146 46.89614858846383))'
        ),
    'paris':
        GEOSGeometry(
            'SRID=4326;POLYGON(('
            '1.6892213123671462 49.086733408488925,'
            '2.8317994373671462 49.086733408488925,'
            '2.8317994373671462 48.52233957365349,'
            '1.6892213123671462 48.52233957365349,'
            '1.6892213123671462 49.086733408488925))'
        ),
    'covers-switzerland':
        GEOSGeometry(
            'SRID=4326;POLYGON(('
            '4.96 44.82,'
            '11.49 44.82,'
            '11.49 49.81,'
            '4.96 49.81,'
            '4.96 44.82))'
        )
}

links = {
    'link-1': {
        'rel': 'describedBy',
        'href': 'https://www.example.com/described-by',
        'title': 'This is an extra item link',
        'link_type': 'description'
    }
}

links_invalid = {
    'link-invalid': {
        'title': 'invalid item link relation',
        'rel': 'invalid relation',
        'href': 'not a url',
    }
}

links_hreflanged = {
    'link-1': {
        'title': 'Link with hreflang',
        'rel': 'describedBy',
        'href': 'http://perdu.com/',
        'hreflang': 'de'
    },
    'link-2': {
        'title': 'Link with hreflang',
        'rel': 'copiedFrom',
        'href': 'http://perdu.com/',
        'hreflang': 'fr-CH'
    }
}

items = {
    'item-1': {
        'name': 'item-1',
        'geometry':
            GEOSGeometry(
                json.dumps({
                    "coordinates": [[
                        [5.644711, 46.775054],
                        [5.644711, 48.014995],
                        [6.602408, 48.014995],
                        [7.602408, 49.014995],
                        [5.644711, 46.775054],
                    ]],
                    "type": "Polygon"
                })
            ),
        'properties_title': 'My item 1',
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z'),
        'links': links.values()
    },
    'item-2': {
        'name': 'item-2',
        'geometry':
            GEOSGeometry(
                json.dumps({
                    "coordinates": [[
                        [5.644711, 46.775054],
                        [5.644711, 48.014995],
                        [6.602408, 48.014995],
                        [7.602408, 49.014995],
                        [5.644711, 46.775054],
                    ]],
                    "type": "Polygon"
                })
            ),
        'properties_title': 'My item 2',
        'properties_start_datetime': fromisoformat('2020-10-28T13:05:10Z'),
        'properties_end_datetime': fromisoformat('2020-10-28T14:05:10Z')
    },
    'item-invalid': {
        'name': 'item invalid name',
        'geometry': {
            "coordinates": [[
                [10000000, 46.775054],
                [5.644711, 48.014995],
                [6.602408, 48.014995],
                [7.602408, 444444444],
                [5.644711, 46.775054],
            ]],
            "type": "Polygon"
        },
        'properties_title': [23, 56],
        'properties_start_datetime': 'not a datetime',
    },
    'item-invalid-link': {
        'name': 'item-invalid-link',
        'geometry': {
            "coordinates": [[
                [5.644711, 46.775054],
                [5.644711, 48.014995],
                [6.602408, 48.014995],
                [7.602408, 49.014995],
                [5.644711, 46.775054],
            ]],
            "type": "Polygon"
        },
        'properties': {
            'datetime': fromisoformat('2020-10-28T13:05:10Z')
        },
        'links': links_invalid.values()
    },
    'item-hreflang-links': {
        'name': 'item-hreflang-link',
        'geometry':
            GEOSGeometry(
                json.dumps({
                    "coordinates": [[
                        [5.644711, 46.775054],
                        [5.644711, 48.014995],
                        [6.602408, 48.014995],
                        [7.602408, 49.014995],
                        [5.644711, 46.775054],
                    ]],
                    "type": "Polygon"
                })
            ),
        'properties_datetime': fromisoformat('2024-12-05T13:37Z'),
        'links': links_hreflanged.values()
    },
    'item-switzerland': {
        'name': 'item-switzerland',
        'geometry': geometries['switzerland'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z')
    },
    'item-switzerland-west': {
        'name': 'item-switzerland-west',
        'geometry': geometries['switzerland-west'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z')
    },
    'item-switzerland-east': {
        'name': 'item-switzerland-east',
        'geometry': geometries['switzerland-east'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z')
    },
    'item-switzerland-north': {
        'name': 'item-switzerland-north',
        'geometry': geometries['switzerland-north'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z')
    },
    'item-switzerland-south': {
        'name': 'item-switzerland-south',
        'geometry': geometries['switzerland-south'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z')
    },
    'item-paris': {
        'name': 'item-paris',
        'geometry': geometries['paris'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z')
    },
    'item-covers-switzerland': {
        'name': 'item-covers_switzerland',
        'geometry': geometries['covers-switzerland'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z')
    },
    'item-forecast-1': {
        'name': 'item-forecast-1',
        'geometry': geometries['covers-switzerland'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z'),
        'forecast_reference_datetime': fromisoformat('2025-01-01T13:05:10Z'),
        'forecast_horizon': 'PT6H',
        'forecast_duration': 'PT12H',
        'forecast_variable': 'T',
        'forecast_perturbed': 'False',
    },
    'item-forecast-2': {
        'name': 'item-forecast-2',
        'geometry': geometries['covers-switzerland'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z'),
        'forecast_reference_datetime': fromisoformat('2025-02-01T13:05:10Z'),
        'forecast_horizon': 'PT6H',
        'forecast_duration': 'PT12H',
        'forecast_variable': 'T',
        'forecast_perturbed': 'False',
    },
    'item-forecast-3': {
        'name': 'item-forecast-3',
        'geometry': geometries['covers-switzerland'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z'),
        'forecast_reference_datetime': fromisoformat('2025-02-01T13:05:10Z'),
        'forecast_horizon': 'PT3H',
        'forecast_duration': 'PT6H',
        'forecast_variable': 'T',
        'forecast_perturbed': 'False',
    },
    'item-forecast-4': {
        'name': 'item-forecast-4',
        'geometry': geometries['covers-switzerland'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z'),
        'forecast_reference_datetime': fromisoformat('2025-02-01T13:05:10Z'),
        'forecast_horizon': 'PT6H',
        'forecast_duration': 'PT12H',
        'forecast_variable': 'air_temperature',
        'forecast_perturbed': 'True',
    },
    'item-forecast-5': {
        'name': 'item-forecast-5',
        'geometry': geometries['covers-switzerland'],
        'properties_datetime': fromisoformat('2020-10-28T13:05:10Z'),
        'forecast_reference_datetime': fromisoformat('2025-04-01T13:05:10Z'),
        'forecast_horizon': 'PT6H',
        'forecast_duration': 'PT12H',
        'forecast_variable': 'air_temperature',
        'forecast_perturbed': 'False',
    },
}
