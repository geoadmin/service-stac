# Generated by Django 3.1.2 on 2020-10-30 14:24

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0006_auto_20201029_2055'),
    ]

    operations = [
        migrations.RenameField(
            model_name='asset',
            old_name='proj_epsq',
            new_name='proj_epsg',
        ),
    ]