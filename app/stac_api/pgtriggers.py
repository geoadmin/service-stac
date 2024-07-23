import pgtrigger


def auto_variables_triggers(name):
    auto_variables_func = '''
    -- update auto variables
    NEW.etag = gen_random_uuid();
    NEW.updated = now();

    RAISE INFO 'Updated auto fields of %.id=% due to table updates.', TG_TABLE_NAME, NEW.id;

    RETURN NEW;
    '''
    return [
        pgtrigger.Trigger(
            name=f"add_{name}_auto_variables_trigger",
            operation=pgtrigger.Insert,
            when=pgtrigger.Before,
            func=auto_variables_func
        ),
        pgtrigger.Trigger(
            name=f"update_{name}_auto_variables_trigger",
            operation=pgtrigger.Update,
            when=pgtrigger.Before,
            condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*'),
            func=auto_variables_func
        )
    ]


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
    return [
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
    ]


def generates_asset_triggers():
    '''Generates Asset triggers

    Those triggers act on `insert`, `update` and `delete` Asset event and do the followings:
      - Update the `updated` and `etag` fields of the assets and their parents
      - Update the parent collection summaries.
      - Update the parent item `update_interval` by using the minimal aggregation of all of its
        assets

    Returns: tuple
        tuple for all needed triggers
    '''

    class UpdateCollectionSummariesTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [
            ('asset_instance', 'stac_api_asset%ROWTYPE'),
            ('related_collection_id', 'INT'),
            ('collection_summaries', 'RECORD'),
        ]
        func = '''
        asset_instance = COALESCE(NEW, OLD);

        related_collection_id = (
            SELECT collection_id FROM stac_api_item
            WHERE id = asset_instance.item_id
        );

        -- Compute collection summaries
        SELECT
            collection_id,
            array_remove(array_agg(DISTINCT(proj_epsg)), null) AS proj_epsg,
            array_remove(array_agg(DISTINCT(geoadmin_variant)), null) AS geoadmin_variant,
            array_remove(array_agg(DISTINCT(geoadmin_lang)), null) AS geoadmin_lang,
            array_remove(array_agg(DISTINCT(eo_gsd)), null) AS eo_gsd
        INTO collection_summaries
        FROM (
                SELECT item.collection_id, asset.proj_epsg, asset.geoadmin_variant, asset.geoadmin_lang, asset.eo_gsd
                FROM stac_api_item AS item
                    LEFT JOIN stac_api_asset AS asset ON (asset.item_id = item.id)
                WHERE collection_id = related_collection_id
                UNION
                SELECT collection_id, proj_epsg, NULL, NULL, NULL
                FROM stac_api_collectionasset
                WHERE collection_id = related_collection_id
            ) a
        GROUP BY collection_id;

        -- Update related collection (auto variables + summaries)
        UPDATE stac_api_collection SET
            summaries_proj_epsg = collection_summaries.proj_epsg,
            summaries_geoadmin_variant = collection_summaries.geoadmin_variant,
            summaries_geoadmin_lang = collection_summaries.geoadmin_lang,
            summaries_eo_gsd = collection_summaries.eo_gsd
        WHERE id = related_collection_id;

        RAISE INFO 'collection.id=% summaries updated, due to asset.name=% update.',
            related_collection_id, asset_instance.name;

        RETURN asset_instance;
        '''

    class UpdateItemUpdateIntervalTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [
            ('asset_instance', 'stac_api_asset%ROWTYPE'),
            ('item_update_interval', 'RECORD'),
        ]
        func = '''
        asset_instance = COALESCE(NEW, OLD);

        -- Compute item update_interval (minimum aggregation of asset's update_interval)
        SELECT
            COALESCE(MIN(NULLIF(asset.update_interval, -1)), -1) AS min_update_interval
        INTO item_update_interval
        FROM stac_api_asset AS asset
        WHERE asset.item_id = asset_instance.item_id;

        -- Update related item update_interval variables
        UPDATE stac_api_item SET
            update_interval = item_update_interval.min_update_interval
        WHERE id = asset_instance.item_id;

        RAISE INFO 'item.id=% update_interval updated, due to asset.name=% updates.',
            asset_instance.item_id, asset_instance.name;

        RETURN asset_instance;
        '''

    return [
        *auto_variables_triggers('asset'),
        *generate_child_triggers('item', "Asset"),
        UpdateCollectionSummariesTrigger(
            name='update_asset_collection_summaries_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.Condition(
                '''OLD.proj_epsg IS DISTINCT FROM NEW.proj_epsg OR
                OLD.geoadmin_variant IS DISTINCT FROM NEW.geoadmin_variant OR
                OLD.geoadmin_lang IS DISTINCT FROM NEW.geoadmin_lang OR
                OLD.eo_gsd IS DISTINCT FROM NEW.eo_gsd'''
            )
        ),
        UpdateCollectionSummariesTrigger(
            name='add_del_asset_collection_summaries_trigger',
            operation=pgtrigger.Delete | pgtrigger.Insert,
        ),
        UpdateItemUpdateIntervalTrigger(
            name='add_del_asset_item_update_interval_trigger',
            operation=pgtrigger.Insert | pgtrigger.Delete,
        ),
        UpdateItemUpdateIntervalTrigger(
            name='update_asset_item_update_interval_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.
            Condition('OLD.update_interval IS DISTINCT FROM NEW.update_interval'),
        )
    ]


def generate_collection_asset_triggers():
    '''Generates collection asset triggers
    Triggers act on `insert`, `update` and `delete` collection asset event and do the following:
      - Update the `updated` and `etag` fields of the assets and their parents
      - Update the parent collection summaries.
      - Update the parent collection `update_interval` by using the minimal aggregation of all
        of its assets
    Returns: tuple
        tuple for all needed triggers
    '''

    class UpdateCollectionSummariesTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [
            ('asset_instance', 'stac_api_collectionasset%ROWTYPE'),
            ('collection_summaries', 'RECORD'),
        ]
        func = '''
        asset_instance = COALESCE(NEW, OLD);

        -- Compute collection summaries
        SELECT
            a.collection_id,
            array_remove(array_agg(DISTINCT(a.proj_epsg)), null) AS proj_epsg
        INTO collection_summaries
        FROM (
            SELECT item.collection_id, asset.proj_epsg
            FROM stac_api_item AS item
                LEFT JOIN stac_api_asset AS asset ON (asset.item_id = item.id)
            WHERE collection_id = asset_instance.collection_id
            UNION
            SELECT collection_id, proj_epsg
            FROM stac_api_collectionasset
            WHERE collection_id = asset_instance.collection_id
        ) a
        GROUP BY a.collection_id;

        -- Update related collection (auto variables + summaries)
        UPDATE stac_api_collection SET
            summaries_proj_epsg = collection_summaries.proj_epsg
        WHERE id = asset_instance.collection_id;

        RAISE INFO 'collection.id=% summaries updated, due to collection asset.name=% update.',
            asset_instance.collection_id, asset_instance.name;
        RETURN asset_instance;
        '''

    class UpdateCollectionUpdateIntervalTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [
            ('asset_instance', 'stac_api_collectionasset%ROWTYPE'),
        ]
        func = '''
        asset_instance = COALESCE(NEW, OLD);
        -- Update related collection update_interval variables
        -- if new value is lower than existing one.
        UPDATE stac_api_collection SET
            update_interval = COALESCE(LEAST(NULLIF(asset_instance.update_interval, -1), update_interval), -1)
        WHERE id = asset_instance.collection_id;
        RAISE INFO 'collection.id=% update_interval updated, due to collectionasset.name=% updates.',
            asset_instance.collection_id, asset_instance.name;
        RETURN asset_instance;
        '''

    return [
        *auto_variables_triggers('col_asset'),
        *generate_child_triggers('collection', "CollectionAsset"),
        UpdateCollectionSummariesTrigger(
            name='update_col_asset_collection_summaries_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*')
        ),
        UpdateCollectionSummariesTrigger(
            name='add_del_col_asset_collection_summaries_trigger',
            operation=pgtrigger.Delete | pgtrigger.Insert,
        ),
        UpdateCollectionUpdateIntervalTrigger(
            name='add_del_col_asset_col_update_interval_trigger',
            operation=pgtrigger.Insert | pgtrigger.Delete,
        ),
        UpdateCollectionUpdateIntervalTrigger(
            name='update_col_asset_col_update_interval_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*'),
        )
    ]


def generates_item_triggers():
    '''Generates Item triggers

    Those triggers update the `updated` and `etag` fields of the items and their parents on
    update, insert or delete. It also update the collection extent.

    Returns: tuple
        tuple for all needed triggers
    '''

    class UpdateCollectionExtentTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [
            ('item_instance', 'stac_api_item%ROWTYPE'),
            ('collection_extent', 'RECORD'),
        ]
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
            extent_geometry = collection_extent.extent_geometry,
            extent_start_datetime = collection_extent.extent_start_datetime,
            extent_end_datetime = collection_extent.extent_end_datetime
        WHERE id = item_instance.collection_id;

        RAISE INFO 'collection.id=% extent updated, due to item.name=% updates.', item_instance.collection_id, item_instance.name;

        RETURN item_instance;
        '''

    class UpdateCollectionUpdateIntervalTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [
            ('item_instance', 'stac_api_item%ROWTYPE'),
            ('collection_update_interval', 'RECORD'),
        ]
        func = '''
        item_instance = COALESCE(NEW, OLD);

        -- Compute collection update_interval (minimum aggregation of item's update_interval)
        SELECT
            COALESCE(MIN(NULLIF(item.update_interval, -1)), -1) AS min_update_interval
        INTO collection_update_interval
        FROM stac_api_item AS item
        WHERE item.collection_id = item_instance.collection_id;

        -- Update related collection update_interval variables
        UPDATE stac_api_collection SET
            update_interval = collection_update_interval.min_update_interval
        WHERE id = item_instance.collection_id;

        RAISE INFO 'collection.id=% update_interval updated, due to item.name=% updates.',
            item_instance.collection_id, item_instance.name;

        RETURN item_instance;
        '''

    return [
        *auto_variables_triggers('item'),
        *generate_child_triggers('collection', 'Item'),
        UpdateCollectionExtentTrigger(
            name='update_item_collection_extent_trigger',
            operation=pgtrigger.Update,
            # condition=pgtrigger.Condition('OLD.* IS DISTINCT FROM NEW.*')
            condition=pgtrigger.Condition(
                '''NOT ST_EQUALS(OLD.geometry, NEW.geometry) OR
                OLD.properties_start_datetime IS DISTINCT FROM NEW.properties_start_datetime OR
                OLD.properties_end_datetime IS DISTINCT FROM NEW.properties_end_datetime OR
                OLD.properties_datetime IS DISTINCT FROM NEW.properties_datetime'''
            )
        ),
        UpdateCollectionExtentTrigger(
            name='add_del_item_collection_extent_trigger',
            operation=pgtrigger.Delete | pgtrigger.Insert
        ),
        UpdateCollectionUpdateIntervalTrigger(
            name='add_del_item_collection_update_interval_trigger',
            operation=pgtrigger.Insert | pgtrigger.Delete,
        ),
        UpdateCollectionUpdateIntervalTrigger(
            name='update_item_collection_update_interval_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.
            Condition('OLD.update_interval IS DISTINCT FROM NEW.update_interval'),
        )
    ]


def generates_collection_triggers():
    '''Generates Collection triggers

    Those triggers update the `updated` and `etag` fields of the collections on
    update or insert.

    Returns: tuple
        tuple for all needed triggers
    '''

    return [
        *auto_variables_triggers('collection'),
    ]


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

    return [
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
    ]
