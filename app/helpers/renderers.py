from rest_framework.renderers import JSONRenderer


class GeoJSONRenderer(JSONRenderer):
    """ Renders geojson.

    It is used if a client sends an "Accept: application/geo+json" header or uses the
    "format=geojson" query parameter.

    """
    media_type = 'application/geo+json'
    format = 'geojson'
