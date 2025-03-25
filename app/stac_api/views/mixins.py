import logging

from django.conf import settings
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from django.utils.cache import patch_cache_control
from django.utils.cache import patch_response_headers
from django.utils.http import unquote
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework import status
from rest_framework.response import Response

from stac_api.models.collection import Collection
from stac_api.serializers.utils import get_parent_link
from stac_api.utils import get_link
from stac_api.utils import parse_cache_control_header

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
        try:
            # In the upsert we need to get the object and pass it to the serializer. This allow the
            # serializer validator to differentiate between create and update. In create case the
            # instance will be None.
            instance = self.get_object()
        except Http404:
            instance = None
        serializer = self.get_serializer(instance, data=data)
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


class RetrieveModelWithCacheMixin:
    '''Retrieve model instance and set cache settings based on collection cache_control_header field
    '''

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        response = Response(serializer.data)

        patch_collection_cache_control_header(response, self.kwargs['collection_name'])
        return response


def patch_collection_cache_control_header(response, collection_name):
    '''Patch the Cache-Control header of the response based on the related collection
    cache_control_header field.
    '''
    cache_control_header = Collection.objects.values('cache_control_header').get(
        name=collection_name
    )['cache_control_header']
    if cache_control_header:
        patch_cache_control(response, **parse_cache_control_header(cache_control_header))
    # Else do nothing, the default cache settings will be set later on


def patch_collections_aggregate_cache_control_header(response):
    '''Patch the Cache-Control header of the response based on the
    COLLECTIONS_AGGREGATE_CACHE_SECONDS setting

    This function is meant to be used by endpoint that aggregate collections, like the list
    collections endpoint or search endpoint.
    '''
    if settings.COLLECTIONS_AGGREGATE_CACHE_SECONDS == 0:
        add_never_cache_headers(response)
    else:
        patch_response_headers(response, cache_timeout=settings.COLLECTIONS_AGGREGATE_CACHE_SECONDS)
        patch_cache_control(response, public=True)


class AssetUploadAdminMixin:
    upload_template_name = "uploadtemplate.html"
    url_suffix = "_upload"

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "<path:object_id>/change/upload/",
                self.admin_site.admin_view(self.upload_view),
                name=f'{self.model._meta.app_label}_{self.model._meta.model_name}{self.url_suffix}',
            )
        ]
        return my_urls + urls

    def upload_view(self, request, object_id, extra_context=None):
        model = self.model
        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, model._meta, object_id)

        context = dict(
            # Include common variables for rendering the admin template.
            self.admin_site.each_context(request),
            # Anything else you want in the context...
            csrf_token=request.META.get('CSRF_COOKIE'),
            asset_name=obj.name,
            collection_name=obj.get_collection(),
        )

        if hasattr(obj, 'item'):
            context['item_name'] = obj.item.name

        return TemplateResponse(request, self.upload_template_name, context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.model.objects.\
            filter(id=request.resolver_match.kwargs['object_id']).first()

        if getattr(obj, "is_external", False):  #check if the object is external
            return super().change_view(request, object_id, form_url)

        extra_context = extra_context or {}
        property_upload_url = reverse(
            f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}{self.url_suffix}',
            args=[object_id],
        )
        extra_context['property_upload_url'] = property_upload_url
        return super().change_view(request, object_id, form_url, extra_context=extra_context)
