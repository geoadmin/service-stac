import logging
from datetime import datetime
from datetime import timezone

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from rest_framework import generics
from rest_framework.response import Response

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import Item
from stac_api.serializers import AssetSerializer
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import ItemSerializer

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
    serializer_class = CollectionSerializer
    queryset = Collection.objects.all()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {'collections': serializer.data}

        logger.debug('GET list of collections', extra={"request": request, "response": data})

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class CollectionDetail(generics.RetrieveAPIView):
    serializer_class = CollectionSerializer
    lookup_url_kwarg = "collection_name"
    queryset = Collection.objects.all()

    def get_object(self):
        collection_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(collection_name=collection_name)
        obj = get_object_or_404(queryset)
        return obj


class ItemsList(generics.ListAPIView):
    serializer_class = ItemSerializer
    queryset = Item.objects.all()

    def get_queryset(self):
        # filter based on the url
        return Item.objects.filter(collection__collection_name=self.kwargs['collection_name'])

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {
            'type': 'FeatureCollection',
            'timeStamp': datetime.utcnow().replace(tzinfo=timezone.utc),
            'features': serializer.data
        }

        logger.debug('GET list of items', extra={"request": request, "response": data})

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class ItemDetail(generics.RetrieveAPIView):
    serializer_class = ItemSerializer
    lookup_url_kwarg = "item_name"
    queryset = Item.objects.all()

    def get_object(self):
        item_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(item_name=item_name)
        obj = get_object_or_404(queryset)
        return obj


class AssetsList(generics.GenericAPIView):
    serializer_class = AssetSerializer
    queryset = Asset.objects.all()
    pagination_class = None

    def get_queryset(self):
        # filter based on the url
        return Asset.objects.filter(
            collection__collection_name=self.kwargs['collection_name'],
            feature__item_name=self.kwargs['item_name']
        )

    def get(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = serializer.data

        logger.debug('GET list of assets: %s', data, extra={"request": request, "response": data})

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class AssetDetail(generics.RetrieveAPIView):
    serializer_class = AssetSerializer
    lookup_url_kwarg = "asset_name"
    queryset = Asset.objects.all()

    def get_object(self):
        asset_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(asset_name=asset_name)
        obj = get_object_or_404(queryset)
        return obj


class TestHttp500(AssetDetail):

    def get(self, request, *args, **kwargs):
        logger.debug('Test request that raises an exception')

        raise AttributeError('test exception')
