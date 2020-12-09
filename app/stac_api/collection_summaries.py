import logging

import numpy as np

logger = logging.getLogger(__name__)


UPDATE_SUMMARIES_FIELDS = ["eo_gsd", "geoadmin_variant", "proj_epsg"]


def float_in(flt, floats, **kwargs):
    '''
    This function is needed for comparing floats in order to check if a
    given float is member of a list of floats.
    '''
    return np.any(np.isclose(flt, floats, **kwargs))


def update_summaries_on_asset_delete(collection, asset):
    '''
    updates the collection's summaries on an asset's deletion or raises
    errors when this fails.
    Args:
        collection: collection, for which the summaries probably need an update
        asset: asset thats being deleted

        For all the given parameters this function checks, if the corresponding
        parameters of the collection need to be updated. If so, they will be either
        updated or an error will be raised, if updating fails.
    '''
    assets = type(asset).objects.filter(item__collection_id=collection.pk).exclude(id=asset.id)
    if bool(assets):

        if not assets.filter(geoadmin_variant=asset.geoadmin_variant).exists():
            collection.summaries["geoadmin:variant"].remove(asset.geoadmin_variant)
            collection.save()

        if not assets.filter(proj_epsg=asset.proj_epsg).exists():
            collection.summaries["proj:epsg"].remove(asset.proj_epsg)
            collection.summaries["proj:epsg"].sort()
            collection.save()

        if not assets.filter(eo_gsd=asset.eo_gsd).exists():
            collection.summaries["eo:gsd"].remove(asset.eo_gsd)
            collection.summaries["eo:gsd"].sort()
            collection.save()

    else:
        # asset was the last item in the collection
        collection.summaries["geoadmin:variant"] = []
        collection.summaries["proj:epsg"] = []
        collection.summaries["eo:gsd"] = []
        collection.save()


def update_summaries_on_asset_insert(collection, asset):
    '''
    updates the collection's summaries on an asset's insertion or raises
    errors when this fails.
    Args:
        collection: collection, for which the summaries probably need an update
        asset: asset thats being inserted
        For all the given parameters this function checks, if the corresponding
        parameters of the collection need to be updated. If so, they will be either
        updated or an error will be raised, if updating fails.
    '''
    if asset.geoadmin_variant and \
        asset.geoadmin_variant not in collection.summaries["geoadmin:variant"]:
        collection.summaries["geoadmin:variant"].append(asset.geoadmin_variant)
        collection.summaries["geoadmin:variant"].sort()
        collection.save()

    if asset.proj_epsg and \
            asset.proj_epsg not in collection.summaries["proj:epsg"]:
        collection.summaries["proj:epsg"].append(asset.proj_epsg)
        collection.summaries["proj:epsg"].sort()
        collection.save()

    if asset.eo_gsd and not float_in(asset.eo_gsd, collection.summaries["eo:gsd"]):
        collection.summaries["eo:gsd"].append(asset.eo_gsd)
        collection.summaries["eo:gsd"].sort()
        collection.save()


def update_summaries_on_asset_update(collection, asset, old_values):
    '''
    updates the collection's summaries on an asset's update or raises
    errors when this fails.
    Args:
        collection: collection, for which the summaries probably need an update
        asset: asset thats being updated
        old_values: (optional) list with the original values of asset's
        eo_gsd, geoadmin_variant and proj_epsg.
        For all the given parameters this function checks, if the corresponding
        parameters of the collection need to be updated. If so, they will be either
        updated or an error will be raised, if updating fails.
    '''

    original_eo_gsd = old_values[0]
    original_geoadmin_variant = old_values[1]
    original_proj_epsg = old_values[2]

    assets = None

    if original_geoadmin_variant != asset.geoadmin_variant:

        if (
            asset.geoadmin_variant and
            asset.geoadmin_variant not in collection.summaries["geoadmin:variant"]
        ):
            collection.summaries["geoadmin:variant"].append(asset.geoadmin_variant)

        # check if the asset's original value is still present in other
        # assets and can remain in the summaries or has to be deleted:
        assets = type(asset).objects.filter(item__collection_id=collection.pk).exclude(id=asset.id)
        if not bool(assets) or \
            not assets.filter(geoadmin_variant=original_geoadmin_variant).exists():
            collection.summaries["geoadmin:variant"].remove(original_geoadmin_variant)

        collection.summaries["geoadmin:variant"].sort()
        collection.save()

    if original_proj_epsg != asset.proj_epsg:

        if asset.proj_epsg and \
            asset.proj_epsg not in collection.summaries["proj:epsg"]:
            collection.summaries["proj:epsg"].append(asset.proj_epsg)

        if assets is None:
            assets = type(asset).objects.filter(item__collection_id=collection.pk
                                               ).exclude(id=asset.id)

        if not bool(assets) or \
            not assets.filter(proj_epsg=original_proj_epsg).exists():
            collection.summaries["proj:epsg"].remove(original_proj_epsg)

        collection.summaries["proj:epsg"].sort()
        collection.save()

    if original_eo_gsd != asset.eo_gsd:

        if asset.eo_gsd and not float_in(asset.eo_gsd, collection.summaries["eo:gsd"]):
            collection.summaries["eo:gsd"].append(asset.eo_gsd)

        if assets is None:
            assets = type(asset).objects.filter(item__collection_id=collection.pk
                                               ).exclude(id=asset.id)

        if not bool(assets) or  \
            not assets.filter(eo_gsd=original_eo_gsd).exists():
            collection.summaries["eo:gsd"].remove(original_eo_gsd)

        collection.summaries["eo:gsd"].sort()
        collection.save()


def update_summaries(collection, asset, deleted, old_values=None):
    '''
    updates the collection's summaries when assets are updated or deleted or raises
    errors when this fails.
    Args:
        collection: collection, for which the summaries probably need an update
        asset: asset thats being inserted/updated or deleted
        deleted: true for asset deleteion, false for insertion or update
        old_values: (optional) list with the original values of asset's
        eo_gsd, geoadmin_variant and proj_epsg.
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
