import logging

from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import Item

logger = logging.getLogger(__name__)


def validate_collection(kwargs):
    '''Validate that the collection given in request kwargs exists

    Args:
        kwargs: dict
            request kwargs dictionary

    Raises:
        Http404: when the collection doesn't exists
    '''
    if not Collection.objects.filter(name=kwargs['collection_name']).exists():
        logger.error("The collection %s does not exist", kwargs['collection_name'])
        raise Http404(f"The collection {kwargs['collection_name']} does not exist")


def validate_item(kwargs):
    '''Validate that the item given in request kwargs exists and is not expired

    Args:
        kwargs: dict
            request kwargs dictionary

    Raises:
        Http404: when the item doesn't exists
    '''
    if not Item.objects.filter(
        Q(properties_expires=None) | Q(properties_expires__gte=timezone.now()),
        name=kwargs['item_name'],
        collection__name=kwargs['collection_name']
    ).exists():
        logger.error(
            "The item %s is not part of the collection %s",
            kwargs['item_name'],
            kwargs['collection_name']
        )
        raise Http404(
            f"The item {kwargs['item_name']} is not part of the collection "
            f"{kwargs['collection_name']}"
        )


def validate_asset(kwargs):
    '''Validate that the asset given in request kwargs exists

    Args:
        kwargs: dict
            request kwargs dictionary

    Raises:
        Http404: when the asset doesn't exists
    '''
    if not Asset.objects.filter(
        name=kwargs['asset_name'],
        item__name=kwargs['item_name'],
        item__collection__name=kwargs['collection_name']
    ).exists():
        logger.error(
            "The asset %s is not part of the item %s in collection %s",
            kwargs['asset_name'],
            kwargs['item_name'],
            kwargs['collection_name']
        )
        raise Http404(
            f"The asset {kwargs['asset_name']} is not part of "
            f"the item {kwargs['item_name']} in collection {kwargs['collection_name']}"
        )


def validate_renaming(serializer, original_id, id_field='name', extra_log=None):
    '''Validate that the object name is not different from the one defined in
       the data.

    Args:
        serializer: serializer object
            The serializer to derive the data from
        original_id: string
            The id/name derived from the request kwargs
        id_field: string
            The key to get the name/id in the data dict (default 'name')
        extra_log: dict
            Dictionary to pass to the log extra in case of error

    Raises:
        Http400: when the object will be renamed/moved
    '''
    data = serializer.validated_data
    if id_field in data.keys():
        if data[id_field] != original_id:
            message = 'Renaming is not allowed'
            logger.error(message, extra=extra_log)
            raise serializers.ValidationError({'id': _(message)})
