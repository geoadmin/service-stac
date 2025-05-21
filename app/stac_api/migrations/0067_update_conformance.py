from django.db import migrations


def update_conformance(apps, schema_editor):
    # Add item-search conformance
    LandingPage = apps.get_model("stac_api", "LandingPage")
    lp = LandingPage.objects.get(version='v1')
    lp.conformsTo = [
        'https://api.stacspec.org/v1.0.0/core',
        'https://api.stacspec.org/v1.0.0/collections',
        'https://api.stacspec.org/v1.0.0/ogcapi-features',
        'https://api.stacspec.org/v1.0.0/item-search',
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core',
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30',
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson',
    ]
    lp.save()


def reverse_update_conformance(apps, schema_editor):
    # Remove item-search conformance
    LandingPage = apps.get_model("stac_api", "LandingPage")
    lp = LandingPage.objects.get(version='v1')
    lp.conformsTo = [
        'https://api.stacspec.org/v1.0.0/core',
        'https://api.stacspec.org/v1.0.0/collections',
        'https://api.stacspec.org/v1.0.0/ogcapi-features',
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core',
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30',
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson',
    ]
    lp.save()


class Migration(migrations.Migration):
    dependencies = [
        ("stac_api", "0066_collectionasset_is_external"),
    ]

    operations = [migrations.RunPython(update_conformance, reverse_update_conformance)]
