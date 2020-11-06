# Generated by Django 3.1.3 on 2020-11-09 12:34

import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0019_auto_20201109_0919'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='collection',
            name='bbox',
        ),
        migrations.AlterField(
            model_name='collection',
            name='extent_geometry',
            field=django.contrib.gis.db.models.fields.PolygonField(blank=True, default=None, editable=False, null=True, srid=4326),
        ),
    ]
