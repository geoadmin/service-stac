import logging

from rest_framework import generics

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from stac_api.models import Collection
from stac_api.serializers import CollectionSerializer

logger = logging.getLogger(__name__)


def landing_page(request):
    url_base = request.build_absolute_uri()
    # Somehow yapf 0.30.0 cannot format the data dictionary nicely with the links embedded array
    # it split the first key: value into two lines and add wrong indentation to the links items
    # therefore we disable yapf for this line here (see https://github.com/google/yapf/issues/392)
    # yapf: disable
    data = {
        "description": "Data Catalog of the Swiss Federal Spatial Data Infrastructure",
        "id": "ch",
        "stac_version": "0.9.0",
        "title": "data.geo.admin.ch",
        "links": [{
            "href": url_base,
            "rel": "self",
            "type": "application/json",
            "title": "this document",
        }, {
            "href": f"{url_base}api.html",
            "rel": "service-doc",
            "type": "text/html",
            "title": "the API documentation"
        }, {
            "href": f"{url_base}conformance",
            "rel": "conformance",
            "type": "application/json",
            "title": "OGC API conformance classes implemented by this server"
        }, {
            "href": f"{url_base}collections",
            "rel": "data",
            "type": "application/json",
            "title": "Information about the feature collections"
        }, {
            "href": f"{url_base}search",
            "rel": "search",
            "type": "application/json",
            "title": "Search across feature collections"
        }]
    }
    # yapf: enable

    logger.debug('Landing page', extra={'request': request, 'response': data})

    return JsonResponse(data)


def checker(request):
    data = {"success": True, "message": "OK"}

    return JsonResponse(data)


class CollectionList(generics.ListAPIView):
    '''
    collections endpoint
    '''
    # TODO: restrict the visible fields in ListView if possible # pylint: disable=fixme
    # seems to be tricky. Would need dynamic serializers or different serializers
    # one for ListView and one for the DetailView..
    # working on it..
    serializer_class = CollectionSerializer
    queryset = Collection.objects.all()


class CollectionDetail(generics.RetrieveAPIView):
    '''
    Returns a detail view of the collection instance with all its properties
    '''
    serializer_class = CollectionSerializer
    lookup_url_kwarg = "collection_name"
    queryset = Collection.objects.all()

    def get_object(self):
        collection_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(collection_name=collection_name)
        obj = get_object_or_404(queryset)
        return obj
