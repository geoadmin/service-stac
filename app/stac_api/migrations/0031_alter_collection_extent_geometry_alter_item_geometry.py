# Generated by Django 5.0.6 on 2024-06-11 06:42

import django.contrib.gis.db.models.fields
from django.db import migrations

import stac_api.validators


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0030_alter_asset_media_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='collection',
            name='extent_geometry',
            field=django.contrib.gis.db.models.fields.GeometryField(
                blank=True, default=None, editable=False, null=True, srid=4326
            ),
        ),
        migrations.AlterField(
            model_name='item',
            name='geometry',
            field=django.contrib.gis.db.models.fields.GeometryField(
                default=
                'SRID=4326;POLYGON ((5.96 45.82, 5.96 47.81, 10.49 47.81, 10.49 45.82, 5.96 45.82))',
                srid=4326,
                validators=[stac_api.validators.validate_geometry]
            ),
        ),
    ]