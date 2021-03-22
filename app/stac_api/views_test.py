import logging

from rest_framework import generics

from stac_api.models import LandingPage

logger = logging.getLogger(__name__)


class TestHttp500(generics.GenericAPIView):
    queryset = LandingPage.objects.all()

    def get(self, request, *args, **kwargs):
        logger.debug('Test request that raises an exception')

        raise AttributeError('test exception')
