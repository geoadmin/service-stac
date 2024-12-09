# Generated by Django 5.0.8 on 2024-10-09 11:45

from django.db import migrations


def add_landing_page_version(apps, schema_editor):
    LandingPage = apps.get_model("stac_api", "LandingPage")
    lp = LandingPage.objects.get(version='v1')
    lp.conformsTo.insert(2, 'https://api.stacspec.org/v1.0.0/ogcapi-features')
    lp.save()


def reverse_landing_page_version(apps, schema_editor):
    # Remove the landing page v0.9
    LandingPage = apps.get_model("stac_api", "LandingPage")
    lp = LandingPage.objects.get(version='v1')
    lp.conformsTo.remove('https://api.stacspec.org/v1.0.0/ogcapi-features')
    lp.save()


class Migration(migrations.Migration):
    dependencies = [
        ("stac_api", "0053_alter_asset_media_type_and_more"),
    ]

    operations = [migrations.RunPython(add_landing_page_version, reverse_landing_page_version)]