import logging

from rest_framework import generics

from stac_api.models import LandingPage
from stac_api.views import CollectionDetail

logger = logging.getLogger(__name__)


class TestHttp500(generics.GenericAPIView):
    queryset = LandingPage.objects.all()

    def get(self, request, *args, **kwargs):
        logger.debug('Test request that raises an exception')

        raise AttributeError('test exception')


class TestCollectionUpsertHttp500(CollectionDetail):

    def perform_upsert(self, serializer, lookup):
        serializer.upsert(**lookup)
        raise AttributeError('test exception')
