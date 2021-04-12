import logging

from django.http import Http404
from django.utils.translation import gettext_lazy as _

from rest_framework.exceptions import ValidationError

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
    '''Validate that the item given in request kwargs exists

    Args:
        kwargs: dict
            request kwargs dictionary

    Raises:
        Http404: when the item doesn't exists
    '''
    if not Item.objects.filter(
        name=kwargs['item_name'], collection__name=kwargs['collection_name']
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


def validate_upload_parts(request):
    '''Validate the multiparts upload parts from request
    Args:
        request: HttpRequest

    '''
    if 'parts' not in request.data:
        message = 'Required "parts" attribute is missing'
        logger.error(message, extra={'request': request})
        raise ValidationError({'parts': _(message)}, code='missing')
    if not isinstance(request.data['parts'], list):
        message = f'Required "parts" must be a list, not a {type(request.data["parts"])}'
        logger.error(message, extra={'request': request})
        raise ValidationError({'parts': _(message)}, code='invalid')


def validate_renaming(serializer, id_field='', original_id='', extra_log=None):
    '''Validate that the asset name is not different from the one defined in
       the data.

    Args:
        serializer: serializer object
            The serializer to derive the data from
        id_field: string
            The key to get the name/id in the data dict
        original_id: string
            The id/name derived from the request kwargs
        extra: djangoHttpRequest object
            The request object for logging purposes

    Raises:
        Http400: when the asset will be renamed/moved
    '''
    data = serializer.validated_data
    if id_field in data.keys():
        if data[id_field] != original_id:
            message = 'Renaming object is not allowed'
            logger.error(message, extra={'request': extra_log})
            raise ValidationError(_(message), code='invalid')
