import logging
from collections import OrderedDict

from django.urls import reverse

from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict

logger = logging.getLogger(__name__)


def update_or_create_links(model, instance, instance_type, links_data):
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
        link, created = model.objects.get_or_create(
            **{instance_type: instance},
            rel=link_data["rel"],
            defaults={
                'href': link_data.get('href', None),
                'link_type': link_data.get('link_type', None),
                'title': link_data.get('title', None)
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
        links_ids.append(link.id)
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


def get_relation_links(request, view, view_args):
    '''Returns a list of auto generated relation links

    Returns the self, root and parent auto generated links.

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
    self_url = request.build_absolute_uri(reverse(view, args=view_args))
    return [
        OrderedDict([
            ('rel', 'self'),
            ('href', self_url),
        ]),
        OrderedDict([
            ('rel', 'root'),
            ('href', request.build_absolute_uri(reverse('landing-page'))),
        ]),
        OrderedDict([
            ('rel', 'parent'),
            ('href', self_url.rsplit('/', maxsplit=1)[0]),
        ]),
    ]


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
