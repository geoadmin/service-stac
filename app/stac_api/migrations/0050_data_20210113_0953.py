# Generated by Django 3.1.5 on 2021-01-13 09:53
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def set_asset_empty_string_to_none(apps, schema_editor):
    # We can't import the Asset model directly as it may be a newer
    # version than this migration expects. We use the historical version.
    Asset = apps.get_model('stac_api', 'Asset')
    for asset in Asset.objects.all():
        updated = False
        for field in ['description', 'title', 'geoadmin_variant', 'geoadmin_lang']:
            if getattr(asset, field) == '':
                logger.info(
                    f'Update asset %s empty field %s to None',
                    asset.name,
                    field,
                    extra={
                        'collection': asset.item.collection.name,
                        'item': asset.item.name,
                        'asset': asset.name
                    }
                )
                setattr(asset, field, None)
                updated |= True

        if updated:
            logger.info(
                'Saving asset %s',
                asset.name,
                extra={
                    'collection': asset.item.collection.name,
                    'item': asset.item.name,
                    'asset': asset.name
                }
            )
            asset.save()


def reverse_migration(apps, schema_editor):
    # this method allow reverse migration and does nothing
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0049_auto_20210113_0947'),
    ]

    operations = [
        migrations.RunPython(set_asset_empty_string_to_none, reverse_migration),
    ]