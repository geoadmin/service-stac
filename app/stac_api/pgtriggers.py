import pgtrigger

AUTO_VARIABLES_FUNC = """
-- update auto variables
NEW.etag = gen_random_uuid();
NEW.updated = now();

RAISE INFO 'Updated auto fields of %.id=% due to table updates.', TG_TABLE_NAME, NEW.id;

RETURN NEW;
"""


def generate_child_triggers(parent_name, child_name):
    '''Function that generates two triggers for parent child relation.

    The triggers update the `updated` and `etag` fields of the parent when a child gets inserted,
    updated or deleted.

    Returns: tuple
        Tuple of Trigger
    '''
    child_update_func = """
    -- update related {parent_name}
    UPDATE stac_api_{parent_name} SET
        updated = now(),
        etag = public.gen_random_uuid()
    WHERE id = {child_obj}.{parent_name}_id;

    RAISE INFO 'Parent table {parent_name}.id=% auto fields updated due to child {child_name}.id=% updates.',
        {child_obj}.{parent_name}_id, {child_obj}.id;

    RETURN {child_obj};
    """
    return (
        pgtrigger.Trigger(
            name=f"add_{parent_name}_child_trigger",
            operation=pgtrigger.Insert,
            when=pgtrigger.After,
            func=child_update_func.format(
                parent_name=parent_name, child_obj="NEW", child_name=child_name
            )
        ),
        pgtrigger.Trigger(
            name=f"update_{parent_name}_child_trigger",
            operation=pgtrigger.Update,
            when=pgtrigger.After,
            condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*'),
            func=child_update_func.format(
                parent_name=parent_name, child_obj="NEW", child_name=child_name
            )
        ),
        pgtrigger.Trigger(
            name=f"del_{parent_name}_child_trigger",
            operation=pgtrigger.Delete,
            when=pgtrigger.After,
            func=child_update_func.format(
                parent_name=parent_name, child_obj="OLD", child_name=child_name
            )
        )
    )


def generates_asset_triggers():
    '''Generates Asset triggers

    Those triggers update the `updated` and `etag` fields of the assets and their parents on
    update, insert or delete. It also update the collection summaries.

    Returns: tuple
        tuple for all needed triggers
    '''

    class UpdateCollectionSummariesTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        func = '''
        asset_instance = COALESCE(NEW, OLD);

        related_collection_id = (
            SELECT collection_id FROM stac_api_item
            WHERE id = asset_instance.item_id
        );

        -- Update related item auto variables
        UPDATE stac_api_item SET
            updated = now(),
            etag = gen_random_uuid()
        WHERE id = asset_instance.item_id;

        RAISE INFO 'item.id=% auto fields updated, due to asset.name=% updates.',
            asset_instance.item_id, asset_instance.name;

        -- Compute collection summaries
        SELECT
            item.collection_id,
            array_remove(array_agg(DISTINCT(asset.proj_epsg)), null) AS proj_epsg,
            array_remove(array_agg(DISTINCT(asset.geoadmin_variant)), null) AS geoadmin_variant,
            array_remove(array_agg(DISTINCT(asset.eo_gsd)), null) AS eo_gsd
        INTO collection_summaries
        FROM stac_api_item AS item
            LEFT JOIN stac_api_asset AS asset ON (asset.item_id = item.id)
        WHERE item.collection_id = related_collection_id
        GROUP BY item.collection_id;

        -- Update related collection (auto variables + summaries)
        UPDATE stac_api_collection SET
            updated = now(),
            etag = gen_random_uuid(),
            summaries_proj_epsg = collection_summaries.proj_epsg,
            summaries_geoadmin_variant = collection_summaries.geoadmin_variant,
            summaries_eo_gsd = collection_summaries.eo_gsd
        WHERE id = related_collection_id;

        RAISE INFO 'collection.id=% summaries updated, due to asset.name=% update.',
            related_collection_id, asset_instance.name;

        RETURN asset_instance;
        '''

        def get_declare(self, model):
            return [
                ('asset_instance', 'stac_api_asset%ROWTYPE'),
                ('related_collection_id', 'INT'),
                ('collection_summaries', 'RECORD'),
            ]

    return (
        UpdateCollectionSummariesTrigger(
            name='update_asset_collection_summaries_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*')
        ),
        UpdateCollectionSummariesTrigger(
            name='add_del_asset_collection_summaries_trigger',
            operation=pgtrigger.Delete | pgtrigger.Insert,
        ),
        pgtrigger.Trigger(
            name="add_asset_auto_variables_trigger",
            operation=pgtrigger.Insert,
            when=pgtrigger.Before,
            func=AUTO_VARIABLES_FUNC
        ),
        pgtrigger.Trigger(
            name="update_asset_auto_variables_trigger",
            operation=pgtrigger.Update,
            condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*'),
            when=pgtrigger.Before,
            func=AUTO_VARIABLES_FUNC
        )
    )


def generates_item_triggers():
    '''Generates Item triggers

    Those triggers update the `updated` and `etag` fields of the items and their parents on
    update, insert or delete. It also update the collection extent.

    Returns: tuple
        tuple for all needed triggers
    '''

    class UpdateCollectionExtentTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        func = '''
        item_instance = COALESCE(NEW, OLD);

        -- Compute collection extent
        SELECT
            item.collection_id,
            ST_SetSRID(ST_EXTENT(item.geometry),4326) as extent_geometry,
            MIN(LEAST(item.properties_datetime, item.properties_start_datetime)) as extent_start_datetime,
            MAX(GREATEST(item.properties_datetime, item.properties_end_datetime)) as extent_end_datetime
        INTO collection_extent
        FROM stac_api_item AS item
        WHERE item.collection_id = item_instance.collection_id
        GROUP BY item.collection_id;

        -- Update related collection (auto variables + extent)
        UPDATE stac_api_collection SET
            updated = now(),
            etag = gen_random_uuid(),
            extent_geometry = collection_extent.extent_geometry,
            extent_start_datetime = collection_extent.extent_start_datetime,
            extent_end_datetime = collection_extent.extent_end_datetime
        WHERE id = item_instance.collection_id;

        RAISE INFO 'collection.id=% extent updated, due to item.name=% updates.', item_instance.collection_id, item_instance.name;

        RETURN item_instance;
        '''

        def get_declare(self, model):
            return [
                ('item_instance', 'stac_api_item%ROWTYPE'),
                ('collection_extent', 'RECORD'),
            ]

    return (
        pgtrigger.Trigger(
            name="add_item_auto_variables_trigger",
            operation=pgtrigger.Insert,
            when=pgtrigger.Before,
            func=AUTO_VARIABLES_FUNC
        ),
        pgtrigger.Trigger(
            name="update_item_auto_variables_trigger",
            operation=pgtrigger.Update,
            when=pgtrigger.Before,
            condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*'),
            func=AUTO_VARIABLES_FUNC
        ),
        UpdateCollectionExtentTrigger(
            name='update_item_collection_extent_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*')
        ),
        UpdateCollectionExtentTrigger(
            name='add_del_item_collection_extent_trigger',
            operation=pgtrigger.Delete | pgtrigger.Insert
        )
    )


def generates_collection_triggers():
    '''Generates Collection triggers

    Those triggers update the `updated` and `etag` fields of the collections on
    update or insert.

    Returns: tuple
        tuple for all needed triggers
    '''

    return (
        pgtrigger.Trigger(
            name="add_collection_auto_variables_trigger",
            operation=pgtrigger.Insert,
            when=pgtrigger.Before,
            func=AUTO_VARIABLES_FUNC
        ),
        pgtrigger.Trigger(
            name="update_collection_auto_variables_trigger",
            operation=pgtrigger.Update,
            when=pgtrigger.Before,
            condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*'),
            func=AUTO_VARIABLES_FUNC
        ),
    )


def generates_asset_upload_triggers():
    '''Generates AssetUpload triggers

    Those triggers update `etag` fields of the AssetUpload on
    update or insert.

    Returns: tuple
        tuple for all needed triggers
    '''
    etag_func = """
    -- update AssetUpload auto variable
    NEW.etag = public.gen_random_uuid();

    RETURN NEW;
    """

    return (
        pgtrigger.Trigger(
            name="add_asset_upload_trigger",
            operation=pgtrigger.Insert,
            when=pgtrigger.Before,
            func=etag_func
        ),
        pgtrigger.Trigger(
            name="update_asset_upload_trigger",
            operation=pgtrigger.Update,
            condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*'),
            when=pgtrigger.Before,
            func=etag_func
        ),
    )
