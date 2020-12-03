# Generated by Django 3.1 on 2020-10-13 15:02 # pylint: disable=invalid-name
import django.contrib.postgres.fields
import django.db.models.deletion
from django.contrib.postgres.operations import CreateExtension
from django.db import migrations
from django.db import models

import stac_api.models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        CreateExtension('postgis'),
        migrations.CreateModel(
            name='Collection',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                    )
                ),
                ('crs', models.URLField(default=['http://www.opengis.net/def/crs/OGC/1.3/CRS84'])),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('description', models.TextField()),
                ('start_date', models.DateTimeField(blank=True, null=True)),
                ('end_date', models.DateTimeField(blank=True, null=True)),
                (
                    'southwest',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.FloatField(), blank=True, size=None
                    )
                ),
                (
                    'northeast',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.FloatField(), blank=True, size=None
                    )
                ),
                ('collection_name', models.CharField(max_length=255, unique=True)),
                ('item_type', models.CharField(default='Feature', max_length=20)),
                ('license', models.CharField(max_length=30)),
                (
                    'stac_extension',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=255),
                        default=list,
                        editable=False,
                        size=None
                    )
                ),
                ('stac_version', models.CharField(max_length=10)),
                (
                    'summaries_eo_gsd',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.FloatField(), blank=True, null=True, size=None
                    )
                ),
                (
                    'summaries_proj',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.IntegerField(), blank=True, null=True, size=None
                    )
                ),
                (
                    'geoadmin_variant',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=15),
                        blank=True,
                        null=True,
                        size=None
                    )
                ),
                ('title', models.CharField(blank=True, max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='Keyword',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                    )
                ),
                ('name', models.CharField(max_length=64)),
            ],
        ),
        migrations.CreateModel(
            name='Link',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                    )
                ),
                ('href', models.URLField()),
                ('rel', models.CharField(max_length=30)),
                ('link_type', models.CharField(blank=True, max_length=150)),
                ('title', models.CharField(blank=True, max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='Provider',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                    )
                ),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField()),
                (
                    'roles',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=9), size=None
                    )
                ),
                ('url', models.URLField()),
            ],
        ),
        migrations.CreateModel(
            name='Item',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                    )
                ),
                (
                    'southwest',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.FloatField(), blank=True, size=None
                    )
                ),
                (
                    'northeast',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.FloatField(), blank=True, size=None
                    )
                ),
                ('geometry_coordinates', models.TextField()),
                ('geometry_type', models.CharField(max_length=25)),
                ('item_name', models.CharField(max_length=255, unique=True)),
                ('properties_datetime', models.DateTimeField()),
                (
                    'properties_eo_gsd',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.FloatField(), blank=True, null=True, size=None
                    )
                ),
                ('properties_title', models.CharField(blank=True, max_length=255)),
                (
                    'stac_extension',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=255),
                        default=list,
                        editable=False,
                        size=None
                    )
                ),
                ('stac_version', models.CharField(max_length=10)),
                ('GeoJSON_type', models.CharField(default='Feature', editable=False, max_length=7)),
                ('assets', models.TextField()),
                ('location', models.URLField()),
                (
                    'collection',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to='stac_api.collection'
                    )
                ),
                ('links', models.ManyToManyField(to='stac_api.Link')),
            ],
        ),
        migrations.AddField(
            model_name='collection',
            name='keywords',
            field=models.ManyToManyField(to='stac_api.Keyword'),
        ),
        migrations.AddField(
            model_name='collection',
            name='links',
            field=models.ManyToManyField(to='stac_api.Link'),
        ),
        migrations.AddField(
            model_name='collection',
            name='providers',
            field=models.ManyToManyField(to='stac_api.Provider'),
        ),
        migrations.CreateModel(
            name='Asset',
            fields=[
                ('asset_id', models.BigAutoField(primary_key=True, serialize=False)),
                ('asset_name', models.CharField(max_length=255, unique=True)),
                ('checksum_multihash', models.CharField(max_length=255)),
                ('description', models.TextField()),
                ('eo_gsd', models.FloatField()),
                (
                    'geoadmin_lang',
                    models.CharField(
                        choices=[('de', 'German'), ('it', 'Italian'), ('fr', 'French'),
                                 ('rm', 'Romansh'), ('en', 'English'), ('', '')],
                        default='',
                        max_length=2
                    )
                ),
                (
                    'geoadmin_variant',
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=15), size=None
                    )
                ),
                ('proj', models.IntegerField(null=True)),
                ('title', models.CharField(max_length=255)),
                ('media_type', models.CharField(max_length=200)),
                ('copy_from_href', models.URLField(max_length=255)),
                ('location', models.URLField()),
                (
                    'collection',
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        to='stac_api.collection'
                    )
                ),
                (
                    'feature',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to='stac_api.item'
                    )
                ),
            ],
        ),
    ]
