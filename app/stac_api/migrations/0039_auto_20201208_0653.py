# Generated by Django 3.1.3 on 2020-12-08 06:53

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0038_auto_20201203_1046'),
    ]

    operations = [
        migrations.AlterField(
            model_name='item',
            name='properties_title',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]