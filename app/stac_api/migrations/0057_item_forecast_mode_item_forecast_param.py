# Generated by Django 5.0.8 on 2024-11-11 16:14

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0056_item_forecast_duration'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='forecast_mode',
            field=models.CharField(
                blank=True,
                choices=[('ctrl', 'Control run'), ('perturb', 'Perturbed run')],
                default=None,
                help_text=
                'Denotes whether the data corresponds to the control run or perturbed runs.',
                null=True
            ),
        ),
        migrations.AddField(
            model_name='item',
            name='forecast_param',
            field=models.CharField(
                blank=True,
                help_text=
                'Name of the model parameter that corresponds to the data, e.g. `T` (temperature), `P` (pressure), `U`/`V`/`W` (windspeed in three directions).',
                null=True
            ),
        ),
    ]
