# Generated by Django 3.1 on 2020-10-15 14:04 # pylint: disable=C0321

import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0003_auto_20201015_1348'),
    ]

    operations = [
        migrations.AlterField(
            model_name='item',
            name='coverage',
            field=django.contrib.gis.db.models.fields.MultiPolygonField(
                default=
                'SRID=2056;MULTIPOLYGON(((2317000 913000 0,3057000 913000 0,3057000 1413000 0,2317000 1413000 0,2317000 913000 0)))',
                dim=3,
                srid=2056
            ),
        ),
    ]
