# Generated by Django 4.0.10 on 2023-03-09 13:21

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0024_added_update_interval_field'),
    ]

    operations = [
        migrations.AlterField(
            model_name='collection',
            name='title',
            field=models.CharField(default='unknown', max_length=255),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name='collection',
            index=models.Index(fields=['title'], name='collection_title_idx'),
        ),
    ]
