from django.contrib.postgres.operations import CryptoExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0012_auto_20210709_0734'),
    ]

    operations = [
        CryptoExtension(),
    ]
