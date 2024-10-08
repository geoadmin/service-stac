# Generated by Django 5.0.7 on 2024-07-23 15:14

from django.db import migrations


# The migration SQL in this file was created manually.
class Migration(migrations.Migration):
    migrate_sql = '''
        -- Fill gsd count based on asset values.
        TRUNCATE stac_api_gsdcount;
        INSERT INTO stac_api_gsdcount (collection_id, value, count)
        SELECT item.collection_id, asset.eo_gsd, COUNT(*) AS count
        FROM stac_api_asset asset
            INNER JOIN stac_api_item item ON asset.item_id = item.id
        GROUP BY item.collection_id, asset.eo_gsd;

        -- Fill geoadmin_lang count based on asset values.
        TRUNCATE stac_api_geoadminlangcount;
        INSERT INTO stac_api_geoadminlangcount (collection_id, value, count)
        SELECT item.collection_id, asset.geoadmin_lang, COUNT(*) AS count
        FROM stac_api_asset asset
            INNER JOIN stac_api_item item ON asset.item_id = item.id
        GROUP BY item.collection_id, asset.geoadmin_lang;

        -- Fill geoadmin_variant count based on asset values.
        TRUNCATE stac_api_geoadminvariantcount;
        INSERT INTO stac_api_geoadminvariantcount (collection_id, value, count)
        SELECT item.collection_id, asset.geoadmin_variant, COUNT(*) AS count
        FROM stac_api_asset asset
            INNER JOIN stac_api_item item ON asset.item_id = item.id
        GROUP BY item.collection_id, asset.geoadmin_variant;

        -- Fill proj_epsg count based on asset and collection asset values.
        TRUNCATE stac_api_projepsgcount;
        INSERT INTO stac_api_projepsgcount (collection_id, value, count)
        SELECT collection_id, proj_epsg, COUNT(*) AS count
        FROM (
            SELECT item.collection_id, asset.proj_epsg
            FROM stac_api_asset asset
                INNER JOIN stac_api_item item ON asset.item_id = item.id
            UNION
            SELECT collection_id, proj_epsg
            FROM stac_api_collectionasset
        ) assets
        GROUP BY collection_id, proj_epsg;
        '''

    reverse_sql = '''
        TRUNCATE stac_api_gsdcount;

        TRUNCATE stac_api_geoadminlangcount;

        TRUNCATE stac_api_geoadminvariantcount;

        TRUNCATE stac_api_projepsgcount;
        '''

    dependencies = [
        ('stac_api', '0046_geoadminlangcount_geoadminvariantcount_gsdcount_and_more'),
    ]

    operations = [migrations.RunSQL(sql=migrate_sql, reverse_sql=reverse_sql)]
