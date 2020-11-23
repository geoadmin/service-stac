# Generated by Django 3.1.3 on 2020-11-12 17:10

from django.db import migrations
from django.db import models

import stac_api.models


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0024_data_20201112_0822'),
    ]

    operations = [
        migrations.AlterField(
            model_name='collectionlink',
            name='rel',
            field=models.CharField(max_length=30, validators=[stac_api.models.validate_link_rel]),
        ),
        migrations.AlterField(
            model_name='itemlink',
            name='rel',
            field=models.CharField(max_length=30, validators=[stac_api.models.validate_link_rel]),
        ),
    ]