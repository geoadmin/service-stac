import logging

import numpy as np

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def float_in(flt, floats, **kwargs):
    '''
    This function is needed for comparing floats in order to check if a
    given float is member of a list of floats.
    '''
    return np.any(np.isclose(flt, floats, **kwargs))


def update_summaries_on_asset_delete(collection, asset):
    try:
        asset_qs = asset.__class__.objects.filter(item__collection_id=collection.pk
                                                 ).exclude(id=asset.id)
        if bool(asset_qs):

            if not asset_qs.filter(geoadmin_variant=asset.geoadmin_variant).exists():
                collection.summaries["geoadmin:variant"].remove(asset.geoadmin_variant)
                collection.summaries["geoadmin:variant"].sort()
                collection.save()

            if not asset_qs.filter(proj_epsg=asset.proj_epsg).exists():
                collection.summaries["proj:epsg"].remove(asset.proj_epsg)
                collection.summaries["proj:epsg"].sort()
                collection.save()

            if not asset_qs.filter(eo_gsd=asset.eo_gsd).exists():
                collection.summaries["eo:gsd"].remove(asset.eo_gsd)
                collection.summaries["eo:gsd"].sort()
                collection.save()

        else:
            # asset was the last item in the collection
            collection.summaries["geoadmin:variant"] = []
            collection.summaries["proj:epsg"] = []
            collection.summaries["eo:gsd"] = []
            collection.save()

    except KeyError as err:
        logger.error(
            "Error when updating collection's summaries values due to asset deletion: %s", err
        )
        raise ValidationError(_(
            "Error when updating collection's summaries values due to asset deletion."
        ))


def update_summaries_on_asset_insert(collection, asset):
    try:
        if asset.geoadmin_variant and \
            asset.geoadmin_variant not in collection.summaries["geoadmin:variant"]:
            collection.summaries["geoadmin:variant"].append(asset.geoadmin_variant)

        if asset.proj_epsg and \
                asset.proj_epsg not in collection.summaries["proj:epsg"]:
            collection.summaries["proj:epsg"].append(asset.proj_epsg)

        if asset.eo_gsd and not float_in(asset.eo_gsd, collection.summaries["eo:gsd"]):
            collection.summaries["eo:gsd"].append(asset.eo_gsd)

    except KeyError as err:
        logger.error(
            "Error when updating collection's summaries values due to asset insert: %s", err
        )
        raise ValidationError(_(
            "Error when updating collection's summaries values due to asset insert."
        ))


def update_summaries_on_asset_update(collection, asset, old_values):

    original_eo_gsd = old_values[0]
    original_geoadmin_variant = old_values[1]
    original_proj_epsg = old_values[2]

    asset_qs = None

    try:

        if original_geoadmin_variant != asset.geoadmin_variant:

            if asset.geoadmin_variant and \
            asset.geoadmin_variant not in collection.summaries["geoadmin:variant"]:
                collection.summaries["geoadmin:variant"].append(asset.geoadmin_variant)

            # check if the asset's original value is still present in other
            # assets and can remain in the summaries or has to be deleted:
            asset_qs = asset.__class__.objects.filter(item__collection_id=collection.pk
                                                     ).exclude(id=asset.id)
            if not bool(asset_qs) or \
                not asset_qs.filter(geoadmin_variant=original_geoadmin_variant).exists():
                collection.summaries["geoadmin:variant"].remove(original_geoadmin_variant)

            collection.summaries["geoadmin:variant"].sort()
            collection.save()

        if original_proj_epsg != asset.proj_epsg:

            if asset.proj_epsg and \
                asset.proj_epsg not in collection.summaries["proj:epsg"]:
                collection.summaries["proj:epsg"].append(asset.proj_epsg)

            if asset_qs is None:
                asset_qs = asset.__class__.objects.filter(item__collection_id=collection.pk
                                                         ).exclude(id=asset.id)

            if not bool(asset_qs) or \
                not asset_qs.filter(proj_epsg=original_proj_epsg).exists():
                collection.summaries["proj:epsg"].remove(original_proj_epsg)

            collection.summaries["proj:epsg"].sort()
            collection.save()

        if original_eo_gsd != asset.eo_gsd:

            if asset.eo_gsd and not float_in(asset.eo_gsd, collection.summaries["eo:gsd"]):
                collection.summaries["eo:gsd"].append(asset.eo_gsd)

            if asset_qs is None:
                asset_qs = asset.__class__.objects.filter(item__collection_id=collection.pk
                                                         ).exclude(id=asset.id)

            if not bool(asset_qs) or  \
                not asset_qs.filter(eo_gsd=original_eo_gsd).exists():
                collection.summaries["eo:gsd"].remove(original_eo_gsd)

            collection.summaries["eo:gsd"].sort()
            collection.save()

    except KeyError as err:
        logger.error(
            "Error when updating collection's summaries values due to asset update: %s", err
        )
        raise ValidationError(_(
            "Error when updating collection's summaries values due to asset update."
        ))


def update_summaries(collection, asset, deleted, old_values=None):
    '''
    updates the collection's summaries when assets are updated or deleted or raises
    errors when this fails.
    :param asset_geoadmin_value: asset's value for geoadmin_variant
    :param asset_proj_epsg: asset's value for proj:epsg
    :param asset_eo_gsd: asset's value for asset_eo_gsd
    :param deleted: true if asset is deleted, false if asset is updated
    For all the given parameters this function checks, if the corresponding
    parameters of the collection need to be updated. If so, they will be either
    updated or an error will be raised, if updating fails.
    '''

    if deleted:
        update_summaries_on_asset_delete(collection, asset)
    elif asset.pk is not None:
        update_summaries_on_asset_update(collection, asset, old_values)
    else:
        update_summaries_on_asset_insert(collection, asset)
