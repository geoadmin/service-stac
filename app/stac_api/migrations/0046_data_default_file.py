from django.db import migrations
from django.core.files import File


def set_asset_default_file(apps, schema_editor):
    # We can't import the Asset model directly as it may be a newer
    # version than this migration expects. We use the historical version.
    Asset = apps.get_model('stac_api', 'Asset')
    for asset in Asset.objects.all():
        updated = False
        if asset.file is None:
            print('Update asset %s which has no file' % (asset.name))
            asset.file = File()
            updated = True
        if not asset.file.name:
            print('Update asset %s which has an empty file name' % (asset.name))
            asset.file.name = f'{asset.item.collection.name}/{asset.item.name}/{asset.name}'
            updated = True
        if updated:
            asset.save()
            print('Asset %s saved' % (asset.name))


def reverse_migration(apps, schema_editor):
    # this method allow reverse migration and does nothing
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0045_auto_20201223_1557'),
    ]

    operations = [
        migrations.RunPython(set_asset_default_file, reverse_migration),
    ]
