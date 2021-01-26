import logging

import numpy as np

logger = logging.getLogger(__name__)

UPDATE_SUMMARIES_FIELDS = ["eo_gsd", "geoadmin_variant", "proj_epsg"]


def float_in(flt, floats, **kwargs):
    '''This function is needed for comparing floats in order to check if a
    given float is member of a list of floats.
    '''
    return np.any(np.isclose(flt, floats, **kwargs))


class CollectionSummariesMixin():

    def update_summaries(self, asset, trigger, old_values=None):
        '''Updates the collection's summaries if needed when assets are updated or deleted.

        For all the given parameters this function checks, if the corresponding parameters of the
        collection need to be updated. If so, they will be updated.

        Args:
            asset:
                Asset thats being inserted/updated or deleted
            trigger:
                Asset trigger event, one of 'insert', 'update' or 'delete'
            old_values: (optional)
                List with the original values of asset's [eo_gsd, geoadmin_variant, proj_epsg].

        Returns:
            bool: True if the collection summaries has been updated, false otherwise
        '''

        logger.debug(
            'Collection update summaries: '
            'trigger=%s, asset=%s, old_values=%s, new_values=%s, current_summaries=%s',
            trigger,
            asset,
            old_values,
            [asset.eo_gsd, asset.geoadmin_variant, asset.proj_epsg],
            self.summaries,
            extra={
                'collection': self.name,
                'item': asset.item.name,
                'asset': asset.name,
            },
        )

        if trigger == 'delete':
            return self._update_summaries_on_asset_delete(asset)
        if trigger == 'update':
            return self._update_summaries_on_asset_update(asset, old_values)
        if trigger == 'insert':
            return self._update_summaries_on_asset_insert(asset)
        raise ValueError(f'Invalid trigger parameter: {trigger}')

    def _update_summaries_on_asset_delete(self, asset):
        '''Updates the collection's summaries if needed  on an asset's deletion

        Args:
            asset: asset thats being deleted

            For all the given parameters this function checks, if the corresponding
            parameters of the collection need to be updated. If so, they will be either
            updated or an error will be raised, if updating fails.

        Returns:
            bool: True if the collection summaries has been updated, false otherwise
        '''
        updated = False
        assets = type(asset).objects.filter(item__collection_id=self.pk).exclude(
            id=asset.id
        ).only('geoadmin_variant', 'proj_epsg', 'eo_gsd', 'collection')

        if assets.exists():
            for key, attribute in [('geoadmin:variant', 'geoadmin_variant'),
                                   ('proj:epsg', 'proj_epsg'),
                                   ('eo:gsd', 'eo_gsd')]:
                attribute_value = getattr(asset, attribute)
                if (
                    not assets.filter(**{
                        attribute: attribute_value
                    }).exists() and attribute_value is not None
                ):
                    logger.info(
                        'Removing %s %s from collection summaries',
                        key,
                        attribute_value,
                        extra={
                            'collection': self.name,
                            'item': asset.item.name,
                            'asset': asset.name,
                            'trigger': 'asset-delete'
                        }
                    )
                    self.summaries[key].remove(attribute_value)
                    updated |= True
        else:
            logger.info(
                'Clearing the collection summaries',
                extra={
                    'collection': self.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'trigger': 'asset-delete'
                }
            )
            # asset was the last item in the collection
            self.summaries["geoadmin:variant"] = []
            self.summaries["proj:epsg"] = []
            self.summaries["eo:gsd"] = []
            updated |= True

        return updated

    def _update_summaries_on_asset_insert(self, asset):
        '''Updates the collection's summaries if needed on an asset's insertion

        Args:
            asset: asset thats being inserted
            For all the given parameters this function checks, if the corresponding
            parameters of the collection need to be updated. If so, they will be either
            updated or an error will be raised, if updating fails.

        Returns:
            bool: True if the collection summaries has been updated, false otherwise
        '''
        updated = False
        if (
            asset.geoadmin_variant and
            asset.geoadmin_variant not in self.summaries["geoadmin:variant"]
        ):
            logger.info(
                'Adds geoadmin:variant %s to collection summaries',
                asset.geoadmin_variant,
                extra={
                    'collection': self.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'trigger': 'asset-insert'
                }
            )
            self.summaries["geoadmin:variant"].append(asset.geoadmin_variant)
            self.summaries["geoadmin:variant"].sort()
            updated |= True

        if asset.proj_epsg and asset.proj_epsg not in self.summaries["proj:epsg"]:
            logger.info(
                'Adds proj:epsg %s to collection summaries',
                asset.proj_epsg,
                extra={
                    'collection': self.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'trigger': 'asset-insert'
                }
            )
            self.summaries["proj:epsg"].append(asset.proj_epsg)
            self.summaries["proj:epsg"].sort()
            updated |= True

        if asset.eo_gsd and not float_in(asset.eo_gsd, self.summaries["eo:gsd"]):
            logger.info(
                'Adds eo:gsd %s to collection summaries',
                asset.proj_epsg,
                extra={
                    'collection': self.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'trigger': 'asset-insert'
                }
            )
            self.summaries["eo:gsd"].append(asset.eo_gsd)
            self.summaries["eo:gsd"].sort()
            updated |= True

        return updated

    def _update_summaries_geoadmin_variant_on_update(
        self, assets, asset, geoadmin_variant, original_geoadmin_variant
    ):
        '''Updates the collection's geoadmin:variant summary if needed on an asset's update

        For the given geoadmin:variant parameter this function checks, if the collection's
        geoadmin:variant summary needs to be updated. If so, it will be updated.

        Args:
            assets: QuerySet
                Assets queryset of all other collection's assets (excluding the one that trigger
                this update)
            asset: Asset
                asset thats being updated
            geoadmin_variant: int
                New asset's geoadmin:variant value
            original_geoadmin_variant: int
                Original asset's geoadmin:variant value

        Returns:
            bool: True if the collection summaries has been updated, false otherwise
        '''
        updated = False

        if geoadmin_variant and geoadmin_variant not in self.summaries["geoadmin:variant"]:
            logger.info(
                'Adds geoadmin:variant %s to collection summaries',
                geoadmin_variant,
                extra={
                    'collection': self.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'trigger': 'asset-update'
                }
            )
            self.summaries["geoadmin:variant"].append(geoadmin_variant)
            updated |= True

        # check if the asset's original value is still present in other
        # assets and can remain in the summaries or has to be deleted:
        if ((
            not assets.exists() or
            not assets.filter(geoadmin_variant=original_geoadmin_variant).exists()
        ) and original_geoadmin_variant is not None):
            logger.info(
                'Removes original geoadmin:variant value %s from collection summaries',
                original_geoadmin_variant,
                extra={
                    'collection': self.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'trigger': 'asset-update'
                }
            )
            self.summaries["geoadmin:variant"].remove(original_geoadmin_variant)
            updated |= True

        if updated:
            self.summaries["geoadmin:variant"].sort()

        return updated

    def _update_summaries_proj_epsg_on_update(self, assets, asset, proj_epsg, original_proj_epsg):
        '''Updates the collection's proj:epsg summary if needed on an asset's update

        For the given proj:epsg parameter this function checks, if the collection's proj:epsg
        summary needs to be updated. If so, it will be updated.

        Args:
            assets: QuerySet
                Assets queryset of all other collection's assets (excluding the one that trigger
                this update)
            asset: Asset
                asset thats being updated
            proj_epsg: int
                New asset's proj:epsg value
            original_proj_epsg: int
                Original asset's proj:epsg value

        Returns:
            bool: True if the collection summaries has been updated, false otherwise
        '''
        updated = False

        if proj_epsg and proj_epsg not in self.summaries["proj:epsg"]:
            logger.info(
                'Adds proj:epsg value %s from collection summaries',
                proj_epsg,
                extra={
                    'collection': self.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'trigger': 'asset-update'
                }
            )
            self.summaries["proj:epsg"].append(proj_epsg)
            updated |= True

        if (
            not assets.exists() or not assets.filter(proj_epsg=original_proj_epsg).exists()
        ) and original_proj_epsg is not None:
            logger.info(
                'Removes original proj:epsg value %s from collection summaries',
                original_proj_epsg,
                extra={
                    'collection': self.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'trigger': 'asset-update'
                }
            )
            self.summaries["proj:epsg"].remove(original_proj_epsg)
            updated |= True

        if updated:
            self.summaries["proj:epsg"].sort()

        return updated

    def _update_summaries_eo_gsd_on_update(self, assets, asset, eo_gsd, original_eo_gsd):
        '''Updates the collection's eo:gsd summary if needed on an asset's update

        For the given eo:gsd parameter this function checks, if the collection's eo:gsd summary
        needs to be updated. If so, it will be updated.

        Args:
            assets: QuerySet
                Assets queryset of all other collection's assets (excluding the one that trigger
                this update)
            asset: Asset
                asset thats being updated
            eo_gsd: int
                New asset's eo:gsd value
            original_eo_gsd: int
                Original asset's eo:gsd value

        Returns:
            bool: True if the collection summaries has been updated, false otherwise
        '''
        updated = False

        if eo_gsd and not float_in(eo_gsd, self.summaries["eo:gsd"]):
            logger.info(
                'Adds eo:gsd value %s from collection summaries',
                eo_gsd,
                extra={
                    'collection': self.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'trigger': 'asset-update'
                }
            )
            self.summaries["eo:gsd"].append(eo_gsd)
            updated |= True

        if (
            not assets.exists() or not assets.filter(eo_gsd=original_eo_gsd).exists()
        ) and original_eo_gsd is not None:
            logger.info(
                'Removes original eo:gsd value %s from collection summaries',
                original_eo_gsd,
                extra={
                    'collection': self.name,
                    'item': asset.item.name,
                    'asset': asset.name,
                    'trigger': 'asset-update'
                }
            )
            self.summaries["eo:gsd"].remove(original_eo_gsd)
            updated |= True

        if updated:
            self.summaries["eo:gsd"].sort()

        return updated

    def _update_summaries_on_asset_update(self, asset, old_values):
        '''Updates the collection's summaries if needed on an asset's update

        For all the given parameters this function checks, if the corresponding
        parameters of the collection need to be updated. If so, they will be updated.

        Args:
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

        assets = type(asset).objects.filter(item__collection_id=self.pk).exclude(
            id=asset.id
        ).only('geoadmin_variant', 'proj_epsg', 'eo_gsd', 'collection')

        if original_geoadmin_variant != asset.geoadmin_variant:
            updated |= self._update_summaries_geoadmin_variant_on_update(
                assets, asset, asset.geoadmin_variant, original_geoadmin_variant
            )

        if original_proj_epsg != asset.proj_epsg:
            updated |= self._update_summaries_proj_epsg_on_update(
                assets, asset, asset.proj_epsg, original_proj_epsg
            )

        if original_eo_gsd != asset.eo_gsd:
            updated |= self._update_summaries_eo_gsd_on_update(
                assets, asset, asset.eo_gsd, original_eo_gsd
            )

        return updated
