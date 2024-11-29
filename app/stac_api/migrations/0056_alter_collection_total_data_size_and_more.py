# Generated by Django 5.0.8 on 2024-11-28 16:08

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("stac_api", "0055_alter_asset_file_size_alter_assetupload_file_size_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="collection",
            name="total_data_size",
            field=models.BigIntegerField(blank=True, default=0, null=True),
        ),
        migrations.AlterField(
            model_name="item",
            name="total_data_size",
            field=models.BigIntegerField(blank=True, default=0, null=True),
        ),
    ]
