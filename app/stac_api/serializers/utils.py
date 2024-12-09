import logging
from collections import OrderedDict
from typing import Dict
from typing import List

from django.utils.dateparse import parse_duration
from django.utils.duration import duration_iso_string
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict

from stac_api.models import Collection
from stac_api.models import Item
from stac_api.models import Link
from stac_api.utils import build_asset_href
from stac_api.utils import get_browser_url
from stac_api.utils import get_url

logger = logging.getLogger(__name__)


def update_or_create_links(
    model: type[Link],
    instance: type[Item] | type[Collection],
    instance_type: str,
    links_data: List[Dict]
):
    '''Update or create links for a model

    Update the given links list within a model instance or create them when they don't exists yet.
    Args:
        model: model class on which to update/create links (Collection or Item)
        instance: model instance on which to update/create links
        instance_type: (str) instance type name string to use for filtering ('collection' or 'item')
        links_data: list of links dictionary to add/update
    '''
    links_ids = []
    for link_data in links_data:
        link: Link
        created: bool
        link, created = model.objects.get_or_create(
            **{instance_type: instance},
            rel=link_data["rel"],
            defaults={
                'href': link_data.get('href', None),
                'link_type': link_data.get('link_type', None),
                'title': link_data.get('title', None),
                'hreflang': link_data.get('hreflang', None)
            }
        )
        logger.debug(
            '%s link %s',
            'created' if created else 'updated',
            link.href,
            extra={
                instance_type: instance.name, "link": link_data
            }
        )
        links_ids.append(link.pk)
        # the duplicate here is necessary to update the values in
        # case the object already exists
        link.link_type = link_data.get('link_type', link.link_type)
        link.title = link_data.get('title', link.title)
        link.href = link_data.get('href', link.rel)
        link.full_clean()
        link.save()

    # Delete link that were not mentioned in the payload anymore
    deleted = model.objects.filter(**{instance_type: instance},).exclude(id__in=links_ids).delete()
    logger.info(
        "deleted %d stale links for %s %s",
        deleted[0],
        instance_type,
        instance.name,
        extra={instance_type: instance}
    )


view_relations = {
    'search-list': {
        'parent': 'landing-page',
        'browser': None,
    },
    'collections-list': {
        'parent': 'landing-page',
        'browser': 'browser-catalog',
    },
    'collection-detail': {
        'parent': 'landing-page',
        'browser': 'browser-collection',
    },
    'collection-assets-list': {
        'parent': 'collection-detail',
        'browser': None,
    },
    'collection-asset-detail': {
        'parent': 'collection-detail',
        'browser': None,
    },
    'items-list': {
        'parent': 'collection-detail',
        'browser': 'browser-collection',
    },
    'item-detail': {
        'parent': 'collection-detail',
        'browser': 'browser-item',
    },
    'assets-list': {
        'parent': 'item-detail',
        'browser': None,
    },
    'asset-detail': {
        'parent': 'item-detail',
        'browser': None,
    }
}


def get_parent_link(request, view, view_args=()):
    '''Returns the parent relation link

    Args:
        request: HttpRequest
            request object
        view: string
            name of the view that originate the call
        view_args: list
            args to construct the view path

    Returns: OrderedDict
        Parent link dictionary
    '''

    def parent_args(view, args):
        if view.startswith('collection-asset'):
            return args[:1]
        if view.startswith('item'):
            return args[:1]
        if view.startswith('asset'):
            return args[:2]
        return None

    return OrderedDict([
        ('rel', 'parent'),
        (
            'href',
            get_url(request, view_relations[view]['parent'], args=parent_args(view, view_args))
        ),
    ])


def get_relation_links(request, view, view_args=()):
    '''Returns a list of auto generated relation links

    Returns the self, root, collection, items, parent and alternate auto generated links.

    Args:
        request: HttpRequest
            request object
        view: string
            name of the view that originate the call
        view_args: list
            args to construct the view path

    Returns: list
        List of auto generated links
    '''

    links = [
        OrderedDict([
            ('rel', 'self'),
            ('href', get_url(request, view, args=view_args)),
        ]),
        OrderedDict([
            ('rel', 'root'),
            ('href', get_url(request, 'landing-page')),
        ]),
        get_parent_link(request, view, view_args),
    ]

    if view == 'collection-detail':
        links.append(
            OrderedDict([
                ('rel', 'items'),
                ('href', get_url(request, 'items-list', view_args)),
            ])
        )
    elif view.startswith('item') or view.startswith('asset'):
        links.append(
            OrderedDict([
                ('rel', 'collection'),
                ('href', get_url(request, 'collection-detail', view_args[:1])),
            ])
        )
        if view.startswith('asset'):
            links.append(
                OrderedDict([
                    ('rel', 'item'),
                    ('href', get_url(request, 'item-detail', view_args[:2])),
                ])
            )

    if view_relations[view]['browser']:
        links.append(
            OrderedDict([
                ("rel", "alternate"),
                ("title", "STAC Browser"),
                ("type", "text/html"),
                ("href", get_browser_url(request, view_relations[view]['browser'], *view_args)),
            ])
        )

    return links


class UpsertModelSerializerMixin:
    """Add support for Upsert in serializer
    """

    def upsert(self, look_up, **kwargs):
        """
        Update or insert an instance and return it.

        Args:
            look_up: dict
                Must be a unique query to be used in the objects.update_or_create(**look_up) method.
            **kwargs:
                Extra key=value pairs to pass as validated_data to update_or_create(). For example
                relationships that are not serialized but part of the request path can be given
                as kwargs.
        """
        validated_data = {**self.validated_data, **kwargs}
        self.instance, created = self.update_or_create(look_up, validated_data)
        return self.instance, created

    def update_or_create(self, look_up, validated_data):
        """This method must be implemented by the serializer and must make use of the DB
        objects.update_or_create() method.

        Args:
           look_up: dict
                Must be a unique query to be used in the objects.update_or_create(**look_up)
                method.
            validated_data: dict
                Copy of the validated_data to be used as defaults in the
                objects.update_or_create(defaults=validated_data) method.
        """
        raise NotImplementedError("update_or_create() not implemented")


def filter_null(obj):
    filtered_obj = {}
    if isinstance(obj, OrderedDict):
        filtered_obj = OrderedDict()
    for key, value in obj.items():
        if isinstance(value, dict):
            filtered_obj[key] = filter_null(value)
        # then links array might be empty at this point,
        # but that in the view the auto generated links are added anyway
        elif isinstance(value, list) and key != 'links':
            if len(value) > 0:
                filtered_obj[key] = value
        elif value is not None:
            filtered_obj[key] = value
    return filtered_obj


class NonNullSerializer(serializers.Serializer):
    """Filter fields with null value

    Best practice is to not include (optional) fields whose
    value is None.
    """

    # pylint: disable=abstract-method

    def to_representation(self, instance):
        obj = super().to_representation(instance)
        return filter_null(obj)


class NonNullModelSerializer(serializers.ModelSerializer):
    """Filter fields with null value

    Best practice is to not include (optional) fields whose
    value is None.
    """

    def to_representation(self, instance):
        obj = super().to_representation(instance)
        return filter_null(obj)


class DictSerializer(serializers.ListSerializer):
    '''Represent objects within a dictionary instead of a list

    By default the Serializer with `many=True` attribute represent all objects within a list.
    Here we overwrite the ListSerializer to instead represent multiple objects using a dictionary
    where the object identifier is used as key.

    For example the following list:

        [{
                'name': 'object1',
                'description': 'This is object 1'
            }, {
                'name': 'object2',
                'description': 'This is object 2'
        }]

    Would be represented as follow:

        {
            'object1': {'description': 'This is object 1'},
            'object2': {'description': 'This is object 2'}
        }
    '''

    # pylint: disable=abstract-method

    key_identifier = 'id'

    def to_representation(self, data):
        objects = super().to_representation(data)
        return {obj.pop(self.key_identifier): obj for obj in objects}

    @property
    def data(self):
        ret = super(serializers.ListSerializer, self).data
        return ReturnDict(ret, serializer=self)


class AssetsDictSerializer(DictSerializer):
    '''Assets serializer list to dictionary

    This serializer returns an asset dictionary with the asset name as keys.
    '''
    # pylint: disable=abstract-method
    key_identifier = 'id'


class HrefField(serializers.Field):
    '''Special Href field for Assets'''

    # pylint: disable=abstract-method

    def to_representation(self, value):
        # build an absolute URL from the file path
        request = self.context.get("request")
        path = value.name

        if value.instance.is_external:
            return path
        return build_asset_href(request, path)

    def to_internal_value(self, data):
        return data


class IsoDurationField(serializers.Field):
    '''Handles duration in the ISO 8601 format like "P3DT6H"'''

    def to_internal_value(self, data):
        '''Convert from ISO 8601 (e.g. "P3DT1H") to Python's timedelta'''
        internal = parse_duration(data)
        if internal is None:
            raise serializers.ValidationError(
                code="payload",
                detail={_("Duration doesn't match ISO 8601 format")}
            )
        return internal

    def to_representation(self, value):
        '''Convert from Python's timedelta to ISO 8601 (e.g. "P3DT02H00M00S")'''
        return duration_iso_string(value)
