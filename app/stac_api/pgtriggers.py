from enum import Enum

import pgtrigger


def auto_variables_triggers(name):
    '''Triggers used by various tables to update the `etag` and `updated` fields.'''
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


def child_triggers(parent_name, child_name):
    '''Triggers used by various tables to update the `updated` and `etag` fields
    of the parent table when a child gets inserted, updated or deleted.

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


def asset_counter_trigger(count_table, value_field):
    '''Triggers for the asset table to adjust the 4 counter tables for the asset summaries.

    Args:
         count_table: the table name to be updated (without prefix stac_api_)
         value_field: summary field name on the asset

    Returns:
        List of triggers
    '''

    class DecreaseCounterTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [('asset_instance', 'stac_api_asset%ROWTYPE'), ('related_collection_id', 'INT')]
        func = f'''
        asset_instance = OLD;

        related_collection_id = (
            SELECT collection_id FROM stac_api_item
            WHERE id = asset_instance.item_id
        );

        -- Remove entry when count will reach 0
        DELETE FROM stac_api_{count_table}
        WHERE collection_id = related_collection_id
            AND value = asset_instance.{value_field}
            AND count = 1;

        IF NOT FOUND THEN
        UPDATE stac_api_{count_table}
        SET count = count-1
        WHERE collection_id = related_collection_id
            AND value = asset_instance.{value_field};

        RAISE INFO
            '{count_table} (collection_id, value) (% %) count updated, due to asset.name=% update.',
            related_collection_id, asset_instance.{value_field}, asset_instance.name;

        RETURN asset_instance;
        END IF;

        RAISE INFO
            '{count_table} (collection_id, value) (% %) deleted, due to asset.name=% update.',
            related_collection_id, asset_instance.{value_field}, asset_instance.name;

        RETURN asset_instance;
        '''

    class IncreaseCounterTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [('asset_instance', 'stac_api_asset%ROWTYPE'), ('related_collection_id', 'INT')]
        func = f'''
        asset_instance = NEW;

        related_collection_id = (
            SELECT collection_id FROM stac_api_item
            WHERE id = asset_instance.item_id
        );

        INSERT INTO stac_api_{count_table} (collection_id, value, count)
        VALUES (related_collection_id, asset_instance.{value_field}, 1)
        ON CONFLICT (collection_id, value)
        DO UPDATE SET count = stac_api_{count_table}.count+1;

        RAISE INFO
            '{count_table} (collection_id, value) (% %) count updated, due to asset.name=% update.',
            related_collection_id, asset_instance.{value_field}, asset_instance.name;

        RETURN asset_instance;
        '''

    return [
        DecreaseCounterTrigger(
            name=f'upd_dec_{value_field}_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.
            Condition(f'''OLD.{value_field} IS DISTINCT FROM NEW.{value_field}''')
        ),
        DecreaseCounterTrigger(
            name=f'del_{value_field}_trigger',
            operation=pgtrigger.Delete,
        ),
        IncreaseCounterTrigger(
            name=f'upd_inc_{value_field}_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.
            Condition(f'''OLD.{value_field} IS DISTINCT FROM NEW.{value_field}''')
        ),
        IncreaseCounterTrigger(
            name=f'add_{value_field}_trigger',
            operation=pgtrigger.Insert,
        ),
    ]


def generates_asset_triggers():
    '''Generates Asset triggers

    Those triggers act on `insert`, `update` and `delete` Asset event and do the followings:
      - Update the `updated` and `etag` fields of the assets and their parents
      - Update the parent collection summaries (via counter tables).
      - Update the parent item `update_interval` by using the minimal aggregation of all of its
        assets

    Returns: tuple
        tuple for all needed triggers
    '''

    class ItemUpdateIntervalTrigger(pgtrigger.Trigger):
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
        *child_triggers('item', 'Asset'),
        *asset_counter_trigger('gsdcount', 'eo_gsd'),
        *asset_counter_trigger('geoadminlangcount', 'geoadmin_lang'),
        *asset_counter_trigger('geoadminvariantcount', 'geoadmin_variant'),
        *asset_counter_trigger('projepsgcount', 'proj_epsg'),
        ItemUpdateIntervalTrigger(
            name='add_del_asset_item_update_interval_trigger',
            operation=pgtrigger.Insert | pgtrigger.Delete,
        ),
        ItemUpdateIntervalTrigger(
            name='update_asset_item_update_interval_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.
            Condition('OLD.update_interval IS DISTINCT FROM NEW.update_interval'),
        )
    ]


def generates_collection_asset_triggers():
    '''Generates collection asset triggers
    Triggers act on `insert`, `update` and `delete` collection asset event and do the following:
      - Update the `updated` and `etag` fields of the assets and their parents
      - Update the parent collection summaries.
      - Update the parent collection `update_interval` by using the minimal aggregation of all
        of its assets
    Returns: tuple
        tuple for all needed triggers
    '''

    class CollectionUpdateIntervalTrigger(pgtrigger.Trigger):
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

    class DecreaseCounterTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [('asset_instance', 'stac_api_collectionasset%ROWTYPE'),
                   ('related_collection_id', 'INT')]
        func = '''
        asset_instance = OLD;

        related_collection_id = asset_instance.collection_id;

        -- Remove entry when count will reach 0
        DELETE FROM stac_api_projepsgcount
        WHERE collection_id = related_collection_id
            AND value = asset_instance.proj_epsg
            AND count = 1;

        IF NOT FOUND THEN
        UPDATE stac_api_projepsgcount
        SET count = count-1
        WHERE collection_id = related_collection_id
            AND value = asset_instance.proj_epsg;

        RAISE INFO
            'stac_api_projepsgcount (collection_id, value) (% %) count updated, due to asset.name=% update.',
            related_collection_id, asset_instance.proj_epsg, asset_instance.name;

        RETURN asset_instance;
        END IF;

        RAISE INFO
            'stac_api_projepsgcount (collection_id, value) (% %) deleted, due to asset.name=% update.',
            related_collection_id, asset_instance.proj_epsg, asset_instance.name;

        RETURN asset_instance;
        '''

    class IncreaseCounterTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [('asset_instance', 'stac_api_collectionasset%ROWTYPE'),
                   ('related_collection_id', 'INT')]
        func = '''
        asset_instance = NEW;

        related_collection_id = asset_instance.collection_id;

        INSERT INTO stac_api_projepsgcount (collection_id, value, count)
        VALUES (related_collection_id, asset_instance.proj_epsg, 1)
        ON CONFLICT (collection_id, value)
        DO UPDATE SET count = stac_api_projepsgcount.count+1;

        RAISE INFO
            'projepsgcount (collection_id, value) (% %) count updated, due to asset.name=% update.',
            related_collection_id, asset_instance.proj_epsg, asset_instance.name;

        RETURN asset_instance;
        '''

    return [
        *auto_variables_triggers('col_asset'),
        *child_triggers('collection', "CollectionAsset"),
        DecreaseCounterTrigger(
            name='upd_dec_col_asset_proj_epsg_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.Condition('''OLD.proj_epsg IS DISTINCT FROM NEW.proj_epsg''')
        ),
        DecreaseCounterTrigger(
            name='del_col_asset_proj_epsg_trigger',
            operation=pgtrigger.Delete,
        ),
        IncreaseCounterTrigger(
            name='upd_inc_col_asset_proj_epsg_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.Condition('''OLD.proj_epsg IS DISTINCT FROM NEW.proj_epsg''')
        ),
        IncreaseCounterTrigger(
            name='add_col_asset_proj_epsg_trigger',
            operation=pgtrigger.Insert,
        ),
        CollectionUpdateIntervalTrigger(
            name='add_del_col_asset_col_update_interval_trigger',
            operation=pgtrigger.Insert | pgtrigger.Delete,
        ),
        CollectionUpdateIntervalTrigger(
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

    class CollectionExtentTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [
            ('item_instance', 'stac_api_item%ROWTYPE'),
            ('collection_extent', 'RECORD'),
        ]
        func = '''
        item_instance = COALESCE(NEW, OLD);

        -- Update related collection extent_out_of_sync
        UPDATE stac_api_collection SET
            extent_out_of_sync = TRUE
        WHERE id = item_instance.collection_id;

        RAISE INFO 'collection.id=% extent_out_of_sync updated, due to item.name=% updates.', item_instance.collection_id, item_instance.name;

        RETURN item_instance;
        '''

    class CollectionUpdateIntervalTrigger(pgtrigger.Trigger):
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
        *child_triggers('collection', 'Item'),
        CollectionExtentTrigger(
            name='update_item_collection_extent_trigger',
            operation=pgtrigger.Update,
            condition=pgtrigger.Condition(
                '''NOT ST_EQUALS(OLD.geometry, NEW.geometry) OR
                OLD.properties_start_datetime IS DISTINCT FROM NEW.properties_start_datetime OR
                OLD.properties_end_datetime IS DISTINCT FROM NEW.properties_end_datetime OR
                OLD.properties_datetime IS DISTINCT FROM NEW.properties_datetime'''
            )
        ),
        CollectionExtentTrigger(
            name='add_del_item_collection_extent_trigger',
            operation=pgtrigger.Delete | pgtrigger.Insert
        ),
        CollectionUpdateIntervalTrigger(
            name='add_del_item_collection_update_interval_trigger',
            operation=pgtrigger.Insert | pgtrigger.Delete,
        ),
        CollectionUpdateIntervalTrigger(
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


class SummaryFields(Enum):
    # pylint: disable=invalid-name
    GSD = 'summaries_eo_gsd', 'gsdcount'
    LANGUAGE = 'summaries_geoadmin_lang', 'geoadminlangcount'
    VARIANT = 'summaries_geoadmin_variant', 'geoadminvariantcount'
    PROJ_EPSG = 'summaries_proj_epsg', 'projepsgcount'


def generates_summary_count_triggers(summary_field, count_table):

    class CollectionSummaryTrigger(pgtrigger.Trigger):
        when = pgtrigger.After
        declare = [
            ('count_instance', f'stac_api_{count_table}%ROWTYPE'),
            ('collection_summaries', 'RECORD'),
        ]
        func = f'''
        count_instance = COALESCE(NEW, OLD);

        -- Compute collection summaries
        SELECT
            collection_id,
            array_agg(value) AS values
        INTO collection_summaries
        FROM stac_api_{count_table}
        WHERE count > 0 AND value IS NOT NULL AND collection_id = count_instance.collection_id
        GROUP BY collection_id;

        -- Update related collection (auto variables + summaries)
        UPDATE stac_api_collection
        SET {summary_field} = COALESCE(collection_summaries.values, '{{}}')
        WHERE id = count_instance.collection_id;

        RAISE INFO 'collection.id=% summaries updated',
            count_instance.collection_id;
        RETURN count_instance;
        '''

    return [
        CollectionSummaryTrigger(
            name=f'update_collection_{count_table}_trigger',
            operation=pgtrigger.Update,
            # If the count is larger than 1 for OLD and NEW, the change has no impact on the list of
            # values, so we don't need to recalculate the summary.
            condition=pgtrigger.Condition('NOT (OLD.count > 1 AND NEW.count > 1)')
        ),
        CollectionSummaryTrigger(
            name=f'add_del_collection_{count_table}_trigger',
            operation=pgtrigger.Delete | pgtrigger.Insert,
        )
    ]
