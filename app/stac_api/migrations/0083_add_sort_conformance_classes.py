from django.db import migrations

SORT_CONFORMANCE_CLASSES = [
    'https://api.stacspec.org/v1.1.0/item-search#sort',
    'https://api.stacspec.org/v1.1.0/ogcapi-features#sort',
    'https://api.stacspec.org/v1.1.0/item-search#sortables',
    'http://www.opengis.net/spec/ogcapi-features-5/1.0/conf/sortables',
]


def update_conformance(apps, schema_editor):
    LandingPage = apps.get_model("stac_api", "LandingPage")
    lp = LandingPage.objects.get(version='v1')
    for conformance_class in SORT_CONFORMANCE_CLASSES:
        if conformance_class not in lp.conformsTo:
            lp.conformsTo.append(conformance_class)
    lp.save()


def reverse_update_conformance(apps, schema_editor):
    LandingPage = apps.get_model("stac_api", "LandingPage")
    lp = LandingPage.objects.get(version='v1')
    for conformance_class in SORT_CONFORMANCE_CLASSES:
        if conformance_class in lp.conformsTo:
            lp.conformsTo.remove(conformance_class)
    lp.save()


class Migration(migrations.Migration):

    dependencies = [
        ("stac_api", "0082_alter_collection_stac_extensions_enabled_and_more"),
    ]

    operations = [migrations.RunPython(update_conformance, reverse_update_conformance)]
