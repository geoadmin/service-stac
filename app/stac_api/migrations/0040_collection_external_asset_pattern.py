# Generated by Django 5.0.7 on 2024-07-19 12:44

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0038_collection_allow_external_assets'),
    ]

    operations = [
        migrations.AddField(
            model_name='collection',
            name='external_asset_pattern',
            field=models.CharField(
                blank=True,
                help_text='The allowed regex pattern for external URLs',
                max_length=1024
            ),
        ),
    ]
