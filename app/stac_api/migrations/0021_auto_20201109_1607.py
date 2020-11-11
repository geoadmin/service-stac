# Generated by Django 3.1.3 on 2020-11-09 16:07

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0020_auto_20201109_1234'),
    ]

    operations = [
        migrations.AlterField(
            model_name='collection',
            name='keywords',
            field=models.ManyToManyField(blank=True, to='stac_api.Keyword'),
        ),
        migrations.AlterField(
            model_name='provider',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
    ]