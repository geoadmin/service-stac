from rest_framework import generics
from django.shortcuts import get_object_or_404
from stac_api.models import Collection
from stac_api.serializers import CollectionSerializer


class CollectionList(generics.ListAPIView):
    '''
    collections endpoint
    '''
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
