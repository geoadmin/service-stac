import logging

from rest_framework import mixins
from rest_framework import status
from rest_framework.response import Response

from stac_api.utils import get_link

logger = logging.getLogger(__name__)


class CreateModelMixin(mixins.CreateModelMixin):
    """
    Create a model instance.

    This overwrite the default mixins to add the 'Location' header and also
    the patch the request with the collection.id and/or item.id when available from
    the path parameter.
    """

    def create(self, request, *args, **kwargs):
        if 'collection_name' in self.kwargs:
            request.data['collection'] = self.kwargs['collection_name']
        if 'item_name' in self.kwargs:
            request.data['item'] = self.kwargs['item_name']
        return super().create(request, *args, **kwargs)

    def get_success_headers(self, data):
        try:
            return {'Location': get_link(data['links'], 'self', raise_exception=True)['href']}
        except KeyError as err:
            logger.error('Failed to set the Location header for item creation: %s', err)
            return {}


class UpdateModelMixin(mixins.UpdateModelMixin):
    """
    Update a model instance.

    This overwrite the default mixins patch the request with the collection.id and/or item.id,
    when available from the path parameter.
    """

    def update(self, request, *args, **kwargs):
        if 'collection_name' in self.kwargs:
            request.data['collection'] = self.kwargs['collection_name']
        if 'item_name' in self.kwargs:
            request.data['item'] = self.kwargs['item_name']
        return super().update(request, *args, **kwargs)


class DestroyModelMixin:
    """
    Destroy a model instance.
    """

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {
                "code": status.HTTP_200_OK,
                "description": f"{instance} successfully deleted",
                "links": [{
                    "rel": "parent",
                    "href": request.build_absolute_uri('/'.join(request.path.split('/')[:-1]))
                }]
            },
            status=status.HTTP_200_OK,
        )

    def perform_destroy(self, instance):
        instance.delete()
