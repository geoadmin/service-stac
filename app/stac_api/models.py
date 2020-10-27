import re

import numpy as np

from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# pylint: disable=fixme
# TODO remove this pylint disable once this is done

# st_geometry bbox ch as default
BBOX_CH = (
    'SRID=2056;'
    'MULTIPOLYGON((('
    '2317000 913000 0,'
    '3057000 913000 0,'
    '3057000 1413000 0,'
    '2317000 1413000 0,'
    '2317000 913000 0)))'
)

# I allowed myself to make excessive use of comments below, as this is still work in progress.
# all the comments can be deleted later on

# after discussion with Chris and Tobias:
# stac_extension will be populated with default values that are set to be
# non-editable for the moment. Could be changed, should the need arise.
# The following - a bit complicated approach - hopefully serves to solve the
# error:
# <begin Quote>
# "*ArrayField default should be a callable instead of an
# instance so that it's not shared between all field instances.
# HINT: Use a callable instead, e.g., use `list` instead of `[]`.""
# <end quote>
DEFAULT_STAC_EXTENSIONS = {
    "EO": "eo",
    "PROJ": "proj",
    "VIEW": "view",
    "GEOADMIN-EXTENSION": "https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json"
}


def get_default_stac_extensions():
    return list(dict(DEFAULT_STAC_EXTENSIONS).values())


class Keyword(models.Model):
    name = models.CharField(max_length=64)  # string

    def __str__(self):
        return self.name


class Link(models.Model):
    href = models.URLField()  # string
    rel = models.CharField(max_length=30)  # string
    link_type = models.CharField(blank=True, max_length=150)  # string
    # added link_ to the fieldname, as "type" is reserved
    title = models.CharField(blank=True, max_length=255)  # string

    def __str__(self):
        return '%s: %s' % (self.rel, self.href)


class Provider(models.Model):
    name = models.CharField(blank=False, max_length=200)  # string
    description = models.TextField()  # string
    roles = ArrayField(models.CharField(max_length=9))  # [string]
    # possible roles are licensor, producer, processor or host. Probably it might sense
    url = models.URLField()  # string

    def __str__(self):
        return self.name

    def clean(self):
        ALLOWED_ROLES = ['licensor', 'producer', 'processor', 'host']  # pylint: disable=invalid-name
        for role in self.roles:
            if role not in ALLOWED_ROLES:
                raise ValidationError(_('Incorrectly defined role found'))


# For Collections and Items: No primary key will be defined, so that the auto-generated ones
# will be used by Django. For assets, a primary key is defined as "BigAutoField" due the
# expected large number of assets


class Collection(models.Model):
    crs = ArrayField(
        models.URLField(default="http://www.opengis.net/def/crs/OGC/1.3/CRS84")
    )  # [string]
    created = models.DateTimeField(auto_now_add=True)  # datetime
    updated = models.DateTimeField(auto_now=True)  # datetime
    description = models.TextField()  # string  / intentionally TextField and
    # not CharField to provide more space for the text.
    # TODO: ""description" is required in radiantearth spec, not required in our spec

    # temporal extent will be auto-populated on every item update inside this collection:
    # start_date will be set to oldest date, end_date to most current date
    # start_date = models.DateTimeField(blank=True, null=True)  # will be automatically populated
    # end_date = models.DateTimeField(blank=True, null=True)  # will be automatically populated

    # spatial extent (2D ord 3D):
    # bbox: southwesterly most extent followed by all axes of the northeasterly
    # most extent specified in Longitude/Latitude or Longitude/Latitude/Elevation
    # based on WGS 84.
    # Example that covers the whole Earth: [[-180.0, -90.0, 180.0, 90.0]].
    # Example that covers the whole earth with a depth of 100 meters to a height
    # of 150 meters: [[-180.0, -90.0, -100.0, 180.0, 90.0, 150.0]].

    # after discussion with Chris and Tobias:
    # bbox resp. spatial extent will be auto-generated on collection level everytime
    # when an item inside the collection is updated.
    # the bbox of the collection will be a an envelope ("Umhüllende") of all
    # bboxes of the items inside the collection.
    # furthermore GeoDjango and its functionality will be used for that.
    # TODO: overwrite items save() function accordingly
    # suggestions of fields to be auto-populated:
    extent = models.JSONField() # [Float], auto-populated from items
    collection_name = models.CharField(unique=True, max_length=255)  # string
    # collection_name is what is simply only called "id" in here:
    # http://ltboc.infra.bgdi.ch/static/products/data.geo.admin.ch/apitransactional.html#operation/createCollection
    item_type = models.CharField(default="Feature", max_length=20)  # string

    keywords = models.ManyToManyField(Keyword)
    license = models.CharField(max_length=30)  # string
    links = models.ManyToManyField(Link)
    providers = models.ManyToManyField(Provider)

    stac_extension = ArrayField(
        models.CharField(max_length=255), default=get_default_stac_extensions, editable=False
    )
    stac_version = models.CharField(max_length=10)  # string

    # "summaries" values will be updated on every update of an asset inside the
    # collection
    summaries=models.JSONField()
    #summaries_eo_gsd = ArrayField(models.FloatField(), blank=True, null=True)
    #summaries_proj = ArrayField(models.IntegerField(), blank=True, null=True)
    # after discussion with Chris and Tobias: geoadmin_variant will be an
    # array field of CharFields. Simple validation is done (e.g. no "Sonderzeichen"
    # in array)
    # geoadmin_variant will be also auto-populated on every
    # update of an asset
    #geoadmin_variant = ArrayField(models.CharField(max_length=15), blank=True, null=True)

    title = models.CharField(blank=True, max_length=255)  # string

    def __str__(self):
        return self.collection_name

    def clean(self):
        # TODO: move this check to the items save()
        if self.extent["temporal"]["interval"][0][0] is None and self.extent["temporal"]["interval"][0][1] is None:
            raise ValidationError(_('At least a start date or an end date has to be defined.'))

        # very simple validation, raises error when geoadmin_variant strings contain special
        # characters or umlaut.
        for variant in self.summaries["geoadmin:variant"]:
            if not bool(re.search('^[a-zA-Z0-9]*$', variant)):
                raise ValidationError(_('Property geoadmin:variant not correctly specified.'))


class Item(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    geometry = models.MultiPolygonField(default=BBOX_CH, dim=3, srid=2056)
    item_name = models.CharField(unique=True, blank=False, max_length=255)
    links = models.ManyToManyField(Link)

    # after discussion with Chris and Tobias: for the moment only support
    # proterties: datetime, eo_gsd and title (the rest is hence commented out)
    properties_datetime = models.DateTimeField()
    # properties_eo_bands = model.TextFields(blank=True)  # ? [string]?
    # properties_eo_cloud_cover = models.FloatField(blank=True)  # float
    # eo_gsd is defined on asset level and will be updated here on ever
    # update of an asset inside this item.
    properties_eo_gsd = ArrayField(models.FloatField(), blank=True, null=True)
    # properties_instruments = models.TextField(blank=True)  # [string]
    # properties_license = models.TextField(blank=True)  # string
    # properties_platform = models.TextField(blank=True)  # string
    # properties_providers = models.ManyToManyField(Provider)
    properties_title = models.CharField(blank=True, max_length=255)  # string
    # properties_view_off_nadir = models.FloatField(blank=True)
    # properties_view_sun_azimuth = models.FloatField(blank=True)
    # properties_view_elevation = models.FloatField(blank=True)

    # after discussion with Chris and Tobias:
    # stac_extension will be populated with default values that are set to be
    # non-editable for the moment. Could be changed, should the need arise.
    stac_extension = ArrayField(
        models.CharField(max_length=255), default=get_default_stac_extensions, editable=False
    )

    stac_version = models.CharField(blank=False, max_length=10)
    assets = models.TextField()
    # this is defined as required here:
    # https://github.com/radiantearth/stac-spec/blob/v0.9.0/item-spec/item-spec.md
    # and is meant to contain a dictionary of asset objects than can be
    # downloaded, each with a unique key will be auto-populated on every
    # update of an asset inside this item.
    # TODO: overwrite assets save() function accordingly.
    location = models.URLField()

    def __str__(self):
        return self.item_name

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        # TODO: check if collection's bbox needs to be updated
        # --> this could probably best be done with GeoDjango? (@Tobias)
        # I leave this open for the moment.

        # check if collection's start_ and end_dates need to be updated
        if self.collection.extent["temporal"]["interval"][0][0] is None:

            self.collection.extent["temporal"]["interval"][0][0] = self.properties_datetime
            self.collection.save()

        elif self.properties_datetime < self.collection.extent["temporal"]["interval"][0][0]:

            self.collection.extent["temporal"]["interval"][0][0] = self.properties_datetime
            self.collection.save()

        elif self.properties_datetime > self.collection.extent["temporal"]["interval"][0][1] or \
            self.collection.extent["temporal"]["interval"][0][1] is None:
            self.collection.extent["temporal"]["interval"][0][1] = self.properties_datetime
            self.collection.save()

        super().save(*args, **kwargs)


class Asset(models.Model):
    feature = models.ForeignKey(Item, on_delete=models.CASCADE)
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, blank=True, editable=False)
    id = models.BigAutoField(primary_key=True)

    # using BigIntegerField as primary_key to deal with the expected large number of assets.

    # using "_name" instead of "_id", as "_id" has a default meaning in django
    asset_name = models.CharField(unique=True, blank=False, max_length=255)
    checksum_multihash = models.CharField(blank=False, max_length=255)
    description = models.TextField()
    eo_gsd = models.FloatField()

    class Language(models.TextChoices):
        GERMAN = 'de', _('German')  # pylint: disable=invalid-name
        ITALIAN = 'it', _('Italian')  # pylint: disable=invalid-name
        FRENCH = 'fr', _('French')  # pylint: disable=invalid-name
        ROMANSH = 'rm', _('Romansh')  # pylint: disable=invalid-name
        ENGLISH = 'en', _('English')  # pylint: disable=invalid-name
        NONE = '', _('')  # pylint: disable=invalid-name

    geoadmin_lang = models.CharField(max_length=2, choices=Language.choices, default=Language.NONE)
    # after discussion with Chris and Tobias: geoadmin_variant will be an
    # array field of CharFields. Simple validation is done (e.g. no "Sonderzeichen"
    # in array)
    geoadmin_variant = ArrayField(models.CharField(max_length=15))
    proj = models.IntegerField(null=True)
    title = models.CharField(max_length=255)
    media_type = models.CharField(max_length=200)
    copy_from_href = models.URLField(max_length=255)
    location = models.URLField()

    def __str__(self):
        return self.asset_name

    def clean(self):
        # very simple validation, raises error when geoadmin_variant strings contain special
        # characters or umlaut.
        for variant in self.geoadmin_variant:
            if not bool(re.search('^[a-zA-Z0-9]*$', variant)):
                raise ValidationError(_('Property geoadmin:variant not correctly specified.'))

    # alter save-function, so that the corresponding collection of the parent item of the asset
    # is saved, too.
    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        self.collection = self.feature.collection

        # check if the collection's geoadmin_variant needs to be updated
        for variant in self.geoadmin_variant:
            if not variant in self.feature.collection.summarie["geoadmin:variant"]:
                self.feature.collection.summarie["geoadmin:variant"].append(variant)
                self.feature.collection.save()

        # proj (integer) is defined on collection level as well
        # and eo_gsd (float) on item AND collection level as well.
        # So we need to check if these properties need an update on parent
        # and grandparent level.
        if not self.proj in self.feature.collection.summaries["proj:epsg"]:
            self.feature.collection.summaries["proj:epsg"].append(self.proj)
            self.feature.collection.save()

        # for float-comparison:
        def float_in(f, floats, **kwargs):  # pylint: disable=invalid-name
            return np.any(np.isclose(f, floats, **kwargs))

        if not float_in(self.eo_gsd, self.feature.collection.summaries["eo:gsd"]):
            self.feature.collection.summaries["eo:gsd"].append(self.eo_gsd)
            self.feature.collection.save()

        # TODO: Probably has to be adaptet, depending on how you deal with the properties in items @Brice
        if not float_in(self.eo_gsd, self.feature.properties_eo_gsd):
            self.feature.properties_eo_gsd.append(self.eo_gsd)
            self.feature.collection.save()

        super().save(*args, **kwargs)
