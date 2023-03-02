import logging

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils.cache import add_never_cache_headers
from django.utils.cache import patch_cache_control
from django.utils.cache import patch_response_headers
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework import status
from rest_framework.response import Response

from stac_api.serializers_utils import get_parent_link
from stac_api.utils import get_dynamic_max_age_value
from stac_api.utils import get_link

logger = logging.getLogger(__name__)


def get_success_headers(data):
    try:
        return {'Location': get_link(data['links'], 'self', raise_exception=True)['href']}
    except KeyError as err:
        logger.error('Failed to set the Location header for model creation %s: %s', err, data)
        return {}


class CreateModelMixin:
    """
    Create a model instance.

    This is a copy of the original CreateModelMixin, but the request.data needs to be patched with
    the collection_name and/or item_name depending on the view. This patching cannot be done with
    the original mixin because the request.data is immutable.

    This new mixin allow this patching through the `get_write_request_data` method.

    It also add generic support for the `Location` header.
    """

    def get_write_request_data(self, request, *args, **kwargs):
        return request.data

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = self.get_write_request_data(request, *args, **kwargs)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save()

    def get_success_headers(self, data):
        return get_success_headers(data)


class UpdateInsertModelMixin:
    """
    Update/insert a model instance.

    This is a copy of the original UpdateMixin, but the request.data needs to be patched with
    the collection_name and/or item_name depending on the view. This patching cannot be done with
    the original mixin because the request.data is immutable.

    This new mixin allow this patching through the `get_write_request_data` method.

    It also add the upsert method to perform update_or_create operation
    """

    def get_write_request_data(self, request, *args, partial=False, **kwargs):
        return request.data

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        serializer_kwargs = {'partial': partial}
        instance = self.get_object()
        data = self.get_write_request_data(request, partial=partial, *args, **kwargs)
        serializer = self.get_serializer(instance, data=data, **serializer_kwargs)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}  # pylint: disable=protected-access

        return Response(serializer.data)

    @transaction.atomic
    def upsert(self, request, *args, **kwargs):
        data = self.get_write_request_data(request, *args, **kwargs)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        lookup = {}
        if self.lookup_url_kwarg:
            lookup = {self.lookup_field: self.kwargs[self.lookup_url_kwarg]}
        instance, created = self.perform_upsert(serializer, lookup)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}  # pylint: disable=protected-access

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            headers=self.get_success_headers(serializer.data)
        )

    def perform_update(self, serializer):
        serializer.save()

    def perform_upsert(self, serializer, lookup):
        return serializer.upsert(lookup)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def get_success_headers(self, data):
        return get_success_headers(data)


class DestroyModelMixin:
    """
    Destroy a model instance.

    This is a copy of the original DestroyModelMixin, but return a 200 OK with json payload
    instead of 204 No Content.
    """

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {
                "code": status.HTTP_200_OK,
                "description": f"{instance} successfully deleted",
                "links": [
                    get_parent_link(
                        request,
                        self.get_view_name(),
                        [self.kwargs.get('collection_name'), self.kwargs.get('item_name')]
                    )
                ]
            },
            status=status.HTTP_200_OK,
        )

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError as error:
            logger.error(
                'Failed to delete object %s, object has children: %s',
                instance,
                error,
                extra={'request': self.request._request}  # pylint: disable=protected-access
            )
            child_name = 'unknown'
            if instance.__class__.__name__ == 'Collection':
                child_name = 'items'
            elif instance.__class__.__name__ == 'Item':
                child_name = 'assets'
            raise serializers.ValidationError(
                _(f'Deleting {instance.__class__.__name__} with {child_name} not allowed')
            ) from None


def patch_cache_settings_by_update_interval(response, update_interval):
    max_age = get_dynamic_max_age_value(update_interval)
    if max_age == 0:
        add_never_cache_headers(response)
    elif max_age > 0:
        patch_response_headers(response, cache_timeout=max_age)
        patch_cache_control(response, public=True)


class RetrieveModelDynCacheMixin:
    """
    Retrieve a model instance and set the cache-control header dynamically based on
    `update_interval` model field.
    """

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        response = Response(serializer.data)

        patch_cache_settings_by_update_interval(response, instance.update_interval)

        return response
