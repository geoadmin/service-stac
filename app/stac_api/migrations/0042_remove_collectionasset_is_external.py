# Generated by Django 5.0.7 on 2024-07-22 12:05

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0041_alter_collection_external_asset_pattern'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='collectionasset',
            name='is_external',
        ),
    ]