# Generated by Django 5.0.7 on 2024-07-30 15:26

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("stac_api", "0043_remove_collection_external_asset_pattern_and_more"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="collectionlink",
            unique_together=set(),
        ),
    ]
