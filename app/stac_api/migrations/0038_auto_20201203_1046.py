# Generated by Django 3.1.3 on 2020-12-03 10:46

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0037_conformancepage'),
    ]

    operations = [
        migrations.AlterField(
            model_name='asset',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='asset',
            name='eo_gsd',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='asset',
            name='geoadmin_lang',
            field=models.CharField(
                blank=True,
                choices=[('de', 'German'), ('it', 'Italian'), ('fr', 'French'), ('rm', 'Romansh'),
                         ('en', 'English'), ('', '')],
                default='',
                max_length=2,
                null=True
            ),
        ),
        migrations.AlterField(
            model_name='asset',
            name='proj_epsg',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='asset',
            name='title',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]