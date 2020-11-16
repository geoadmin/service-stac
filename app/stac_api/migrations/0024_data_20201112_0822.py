from django.db import migrations


def update_eo_gsd_type(apps, schema_editor):
    # We can't import the Item model directly as it may be a newer
    # version than this migration expects. We use the historical version.
    Item = apps.get_model('stac_api', 'Item')
    Asset = apps.get_model('stac_api', 'Asset')
    for item in Item.objects.all():
        # Compute the eo:gsd based on the one from the assets
        assets_eo_gsd = [
            asset.eo_gsd
            for asset in Asset.objects.filter(item__item_name=item.item_name)
            if asset.eo_gsd is not None
        ]
        if assets_eo_gsd:
            item.properties_eo_gsd = min(assets_eo_gsd)
        else:
            item.properties_eo_gsd = None
        item.save()


def revert_eo_gsd_type(apps, schema_editor):
    Item = apps.get_model('stac_api', 'Item')
    Asset = apps.get_model('stac_api', 'Asset')
    # for the revert operation we cannot put back the data as before because the
    # field type has changed and we would need a more complex revert operation
    # so here for simplicity we revert to None which is in both model version valid.
    for item in Item.objects.all():
        item.properties_eo_gsd = None
        item.save()


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0023_auto_20201112_0835'),
    ]

    operations = [
        migrations.RunPython(update_eo_gsd_type, revert_eo_gsd_type),
    ]
