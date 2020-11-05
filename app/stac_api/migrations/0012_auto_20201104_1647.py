# Generated by Django 3.1.2 on 2020-11-04 16:47

import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0011_remove_collection_crs'),
    ]

    operations = [
        migrations.RenameField(
            model_name='item',
            old_name='geometry',
            new_name='geometry_old',
        ),
        migrations.RunSQL(
            'ALTER INDEX IF EXISTS stac_api_item_geometry_id RENAME TO stac_api_item_geometry_old_id',
            'ALTER INDEX IF EXISTS stac_api_item_geometry_old_id RENAME TO stac_api_item_geometry_id'
        ),
        migrations.AddField(
            model_name='item',
            name='geometry',
            field=django.contrib.gis.db.models.fields.PolygonField(
                default=
                'SRID=4326;POLYGON ((5.96 45.82, 5.96 47.81, 10.49 47.81, 10.49 45.82, 5.96 45.82))',
                srid=4326
            ),
        ),
    ]