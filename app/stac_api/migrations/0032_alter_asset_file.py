# Generated by Django 5.0.6 on 2024-06-27 09:43

from django.db import migrations

import stac_api.models.general


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0031_alter_collection_extent_geometry_alter_item_geometry'),
    ]

    operations = [
        migrations.AlterField(
            model_name='asset',
            name='file',
            field=stac_api.models.general.DynamicStorageFileField(
                max_length=255, upload_to=stac_api.models.general.upload_asset_to_path_hook
            ),
        ),
    ]
