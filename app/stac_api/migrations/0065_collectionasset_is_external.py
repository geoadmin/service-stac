# Generated by Django 5.0.11 on 2025-03-17 13:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0064_alter_asset_media_type_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='collectionasset',
            name='is_external',
            field=models.BooleanField(default=False, help_text='Whether this asset is hosted externally'),
        ),
    ]
