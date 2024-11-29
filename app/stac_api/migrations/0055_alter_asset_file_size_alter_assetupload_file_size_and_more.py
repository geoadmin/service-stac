# Generated by Django 5.0.8 on 2024-11-28 16:06

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("stac_api", "0054_update_conformance_endpoint"),
    ]

    operations = [
        migrations.AlterField(
            model_name="asset",
            name="file_size",
            field=models.BigIntegerField(blank=True, default=0, null=True),
        ),
        migrations.AlterField(
            model_name="assetupload",
            name="file_size",
            field=models.BigIntegerField(blank=True, default=0, null=True),
        ),
        migrations.AlterField(
            model_name="collectionasset",
            name="file_size",
            field=models.BigIntegerField(blank=True, default=0, null=True),
        ),
        migrations.AlterField(
            model_name="collectionassetupload",
            name="file_size",
            field=models.BigIntegerField(blank=True, default=0, null=True),
        ),
    ]
