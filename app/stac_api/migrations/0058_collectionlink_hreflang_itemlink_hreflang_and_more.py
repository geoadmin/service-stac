# Generated by Django 5.0.8 on 2024-12-05 10:23

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0057_item_forecast_duration_item_forecast_horizon_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='collectionlink',
            name='hreflang',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name='itemlink',
            name='hreflang',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name='landingpagelink',
            name='hreflang',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
    ]
