# Generated by Django 3.1.5 on 2021-02-18 07:26

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0001_initial'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='collection',
            index=models.Index(fields=['name'], name='collection_name_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['name'], name='item_name_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['properties_datetime'], name='item_datetime_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(
                fields=['properties_start_datetime'], name='item_start_datetime_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['properties_end_datetime'], name='item_end_datetime_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['created'], name='item_created_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['updated'], name='item_updated_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['properties_title'], name='item_title_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(
                fields=[
                    'properties_datetime', 'properties_start_datetime', 'properties_end_datetime'
                ],
                name='item_dttme_start_end_dttm_idx'
            ),
        ),
    ]
