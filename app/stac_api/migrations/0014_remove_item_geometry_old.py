# Generated by Django 3.1.2 on 2020-11-04 16:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0013_auto_20201104_1649'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='item',
            name='geometry_old',
        ),
    ]