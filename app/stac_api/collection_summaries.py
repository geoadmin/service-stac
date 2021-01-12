import logging

import numpy as np

logger = logging.getLogger(__name__)

UPDATE_SUMMARIES_FIELDS = ["eo_gsd", "geoadmin_variant", "proj_epsg"]


def float_in(flt, floats, **kwargs):
    '''This function is needed for comparing floats in order to check if a
    given float is member of a list of floats.
    '''
    return np.any(np.isclose(flt, floats, **kwargs))


def update_summaries_on_asset_delete(collection, asset):
    '''Updates the collection's summaries if needed  on an asset's deletion

    Args:
        collection: collection, for which the summaries probably need an update
        asset: asset thats being deleted

        For all the given parameters this function checks, if the corresponding
        parameters of the collection need to be updated. If so, they will be either
        updated or an error will be raised, if updating fails.

    Returns:
        bool: True if the collection summaries has been updated, false otherwise
    '''
    updated = False
    assets = type(asset).objects.filter(item__collection_id=collection.pk).exclude(id=asset.id)
    if assets.exists():

        if not assets.filter(geoadmin_variant=asset.geoadmin_variant).exists():
            collection.summaries["geoadmin:variant"].remove(asset.geoadmin_variant)
            updated |= True

        if not assets.filter(proj_epsg=asset.proj_epsg).exists():
            collection.summaries["proj:epsg"].remove(asset.proj_epsg)
            collection.summaries["proj:epsg"].sort()
            updated |= True

        if not assets.filter(eo_gsd=asset.eo_gsd).exists():
            collection.summaries["eo:gsd"].remove(asset.eo_gsd)
            collection.summaries["eo:gsd"].sort()
            updated |= True

    else:
        # asset was the last item in the collection
        collection.summaries["geoadmin:variant"] = []
        collection.summaries["proj:epsg"] = []
        collection.summaries["eo:gsd"] = []
        updated |= True

    return updated


def update_summaries_on_asset_insert(collection, asset):
    '''Updates the collection's summaries if needed on an asset's insertion

    Args:
        collection: collection, for which the summaries probably need an update
        asset: asset thats being inserted
        For all the given parameters this function checks, if the corresponding
        parameters of the collection need to be updated. If so, they will be either
        updated or an error will be raised, if updating fails.

    Returns:
        bool: True if the collection summaries has been updated, false otherwise
    '''
    updated = False
    if asset.geoadmin_variant and \
        asset.geoadmin_variant not in collection.summaries["geoadmin:variant"]:
        collection.summaries["geoadmin:variant"].append(asset.geoadmin_variant)
        collection.summaries["geoadmin:variant"].sort()
        updated |= True

    if asset.proj_epsg and \
            asset.proj_epsg not in collection.summaries["proj:epsg"]:
        collection.summaries["proj:epsg"].append(asset.proj_epsg)
        collection.summaries["proj:epsg"].sort()
        updated |= True

    if asset.eo_gsd and not float_in(asset.eo_gsd, collection.summaries["eo:gsd"]):
        collection.summaries["eo:gsd"].append(asset.eo_gsd)
        collection.summaries["eo:gsd"].sort()
        updated |= True

    return updated


def update_summaries_geoadmin_variant_on_update(
    collection, assets, geoadmin_variant, original_geoadmin_variant
):
    '''Updates the collection's geoadmin:variant summary if needed on an asset's update

    For the given geoadmin:variant parameter this function checks, if the collection's
    geoadmin:variant summary needs to be updated. If so, it will be updated.

    Args:
        collection: Collection
            Asset's collection, for which the summaries might need an update
        assets: QuerySet
            Assets queryset of all other collection's assets (excluding the one that trigger this
            update)
        geoadmin_variant: int
            New asset's geoadmin:variant value
        original_geoadmin_variant: int
            Original asset's geoadmin:variant value

    Returns:
        bool: True if the collection summaries has been updated, false otherwise
    '''
    updated = False

    if geoadmin_variant and geoadmin_variant not in collection.summaries["geoadmin:variant"]:
        collection.summaries["geoadmin:variant"].append(geoadmin_variant)
        updated |= True

    # check if the asset's original value is still present in other
    # assets and can remain in the summaries or has to be deleted:
    if not assets.exists() or not assets.filter(geoadmin_variant=original_geoadmin_variant
                                               ).exists():
        collection.summaries["geoadmin:variant"].remove(original_geoadmin_variant)
        updated |= True

    if updated:
        collection.summaries["geoadmin:variant"].sort()

    return updated


def update_summaries_proj_epsg_on_update(collection, assets, proj_epsg, original_proj_epsg):
    '''Updates the collection's proj:epsg summary if needed on an asset's update

    For the given proj:epsg parameter this function checks, if the collection's proj:epsg summary
    needs to be updated. If so, it will be updated.

    Args:
        collection: Collection
            Asset's collection, for which the summaries might need an update
        assets: QuerySet
            Assets queryset of all other collection's assets (excluding the one that trigger this
            update)
        proj_epsg: int
            New asset's proj:epsg value
        original_proj_epsg: int
            Original asset's proj:epsg value

    Returns:
        bool: True if the collection summaries has been updated, false otherwise
    '''
    updated = False

    if proj_epsg and proj_epsg not in collection.summaries["proj:epsg"]:
        collection.summaries["proj:epsg"].append(proj_epsg)
        updated |= True

    if not assets.exists() or not assets.filter(proj_epsg=original_proj_epsg).exists():
        collection.summaries["proj:epsg"].remove(original_proj_epsg)
        updated |= True

    if updated:
        collection.summaries["proj:epsg"].sort()

    return updated


def update_summaries_eo_gsd_on_update(collection, assets, eo_gsd, original_eo_gsd):
    '''Updates the collection's eo:gsd summary if needed on an asset's update

    For the given eo:gsd parameter this function checks, if the collection's eo:gsd summary needs
    to be updated. If so, it will be updated.

    Args:
        collection: Collection
            Asset's collection, for which the summaries might need an update
        assets: QuerySet
            Assets queryset of all other collection's assets (excluding the one that trigger this
            update)
        eo_gsd: int
            New asset's eo:gsd value
        original_eo_gsd: int
            Original asset's eo:gsd value

    Returns:
        bool: True if the collection summaries has been updated, false otherwise
    '''
    updated = False

    if eo_gsd and not float_in(eo_gsd, collection.summaries["eo:gsd"]):
        collection.summaries["eo:gsd"].append(eo_gsd)
        updated |= True

    if not assets.exists() or not assets.filter(eo_gsd=original_eo_gsd).exists():
        collection.summaries["eo:gsd"].remove(original_eo_gsd)
        updated |= True

    if updated:
        collection.summaries["eo:gsd"].sort()

    return updated


def update_summaries_on_asset_update(collection, asset, old_values):
    '''Updates the collection's summaries if needed on an asset's update

    For all the given parameters this function checks, if the corresponding
    parameters of the collection need to be updated. If so, they will be updated.

    Args:
        collection: Collection
            collection, for which the summaries probably need an update
        asset: Asset
            asset thats being updated
        old_values: list (optional)
            list with the original values of asset's; [eo_gsd, geoadmin_variant, proj_epsg].

    Returns:
        bool: True if the collection summaries has been updated, false otherwise
    '''
    updated = False
    original_eo_gsd = old_values[0]
    original_geoadmin_variant = old_values[1]
    original_proj_epsg = old_values[2]

    assets = type(asset).objects.filter(item__collection_id=collection.pk).exclude(id=asset.id)

    if original_geoadmin_variant != asset.geoadmin_variant:
        updated |= update_summaries_geoadmin_variant_on_update(
            collection, assets, asset.geoadmin_variant, original_geoadmin_variant
        )

    if original_proj_epsg != asset.proj_epsg:
        updated |= update_summaries_proj_epsg_on_update(
            collection, assets, asset.proj_epsg, original_proj_epsg
        )

    if original_eo_gsd != asset.eo_gsd:
        updated |= update_summaries_eo_gsd_on_update(
            collection, assets, asset.eo_gsd, original_eo_gsd
        )

    return updated
