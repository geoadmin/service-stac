# Generated by Django 3.1.3 on 2020-12-02 13:34

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0035_remove_item_properties_eo_gsd'),
    ]

    operations = [
        migrations.RenameField(
            model_name='collection',
            old_name='cache_end_datetime',
            new_name='extent_end_datetime',
        ),
        migrations.RenameField(
            model_name='collection',
            old_name='cache_start_datetime',
            new_name='extent_start_datetime',
        ),
    ]