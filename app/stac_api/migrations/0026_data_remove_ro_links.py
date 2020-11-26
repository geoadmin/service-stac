from django.db import migrations


def removed_read_only_links(apps, schema_editor):
    # Removed all read only links that were manually added. Now these links
    # are automatically generated.
    # We can't import the Item model directly as it may be a newer
    # version than this migration expects. We use the historical version.
    CollectionLink = apps.get_model('stac_api', 'CollectionLink')
    ItemLink = apps.get_model('stac_api', 'ItemLink')
    for link in CollectionLink.objects.all():
        if link.rel in ['self', 'root', 'parent', 'items']:
            link.delete()

    for link in ItemLink.objects.all():
        if link.rel in ['self', 'root', 'parent', 'collection']:
            link.delete()


def reverse_migration(apps, schema_editor):
    # this method allow reverse migration and does nothing
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0025_auto_20201112_1710'),
    ]

    operations = [
        migrations.RunPython(removed_read_only_links, reverse_migration),
    ]
