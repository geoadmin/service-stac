from django.core.files import File
from django.db import migrations


def rename_asset_old_media_types(apps, schema_editor):
    # We can't import the Asset model directly as it may be a newer
    # version than this migration expects. We use the historical version.
    Asset = apps.get_model('stac_api', 'Asset')
    for asset in Asset.objects.all():
        updated = False
        if asset.media_type == "application/x.asc+zip":
            print('Update asset %s ' % (asset.name))
            asset.media_type = "application/x.ascii-grid+zip"
            updated = True
        if asset.media_type == "application/x.asc-grid+zip":
            print('Update asset %s ' % (asset.name))
            asset.media_type = "application/x.ascii-xyz+zip"
            updated = True
        if updated:
            asset.save()
            print('Asset %s saved' % (asset.name))


def reverse_migration(apps, schema_editor):
    # this method allow reverse migration and does nothing
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0051_auto_20210119_1336'),
    ]

    operations = [
        migrations.RunPython(rename_asset_old_media_types, reverse_migration),
    ]
