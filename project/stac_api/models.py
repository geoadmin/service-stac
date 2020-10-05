from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

# pylint: disable=fixme
# TODO remove this pylint disable once this is done

# st_geometry bbox ch
BBOX_CH = 'POLYGON((2317000 913000,3057000 913000,3057000 1413000,2317000 1413000,2317000 913000))'

# I allowed myself to make excessive use of comments below, as this is still work in progress.
# all the comments can be deleted later on

# For Collections and Items: No primary key will be defined, so that the auto-generated ones
# will be used by Django. For assets, a primary key is defined as "PositiveBigInteger" due the
# expected large number of assets


class Collection(models.Model):
    crs = models.URLField(default=["http://www.opengis.net/def/crs/OGC/1.3/CRS84"])  # [string]
    created = models.DateTimeField(auto_now_add=True)  # datetime
    updated = models.DateTimeField(auto_now=True)  # datetime
    description = models.TextField()  # string
    # --> TODO: ""description" is required in radiantearth spec, not required in our spec

    # temporal extent is defined by a [[datetime|null]]. Open date ranges are
    # supported. Either start or end date can be nulled, e.g.:
    # [["2009-01-01T00:00:00Z", null]]
    start_date = models.DateTimeField(null=True)
    end_date = models.DateTimeField(null=True)

    # spatial extent (2D ord 3D):
    # bbox: southwesterly most extent followed by all axes of the northeasterly
    # most extent specified in Longitude/Latitude or Longitude/Latitude/Elevation
    # based on WGS 84.
    # Example that covers the whole Earth: [[-180.0, -90.0, 180.0, 90.0]].
    # Example that covers the whole earth with a depth of 100 meters to a height
    # of 150 meters: [[-180.0, -90.0, -100.0, 180.0, 90.0, 150.0]].
    SW_lon = models.FloatField()
    SW_lat = models.FloatField()
    SW_elev = models.FloatField(blank=True)
    NE_lon = models.FloatField()
    NE_lat = models.FloatField()
    NE_elev = models.FloatField(blank=True)

    collection_name = models.TextField(unique=True, default="")  # string
    # collection_name is what is simply only called "id" in here:
    # http://ltboc.infra.bgdi.ch/static/products/data.geo.admin.ch/apitransactional.html#operation/createCollection
    itemType = models.TextField(default="Feature")  # string

    # The field formerly known as "Keywords" has been "sourced out" to a
    # separate Keyword class with many-to-many relations to the Collection objects

    license = models.TextField()  # string

    # link objects
    self_href = models.URLField()  # string
    self_rel = models.TextField(default="self", editable=False)  # string
    self_type = models.TextField(blank=True)  # string
    self_title = models.TextField(blank=True)  # string

    root_href = models.URLField()  # string
    root_rel = models.TextField(default="root", editable=False)  # string
    root_type = models.TextField(blank=True)  # string
    root_title = models.TextField(blank=True)  # string

    item_href = models.URLField()  # string
    item_rel = models.TextField(default="item", editable=False)  # string
    item_type = models.TextField(blank=True)  # string
    item_title = models.TextField(blank=True)  # string

    license_href = models.URLField()  # string
    license_rel = models.TextField(default="license", editable=False)  # string
    license_type = models.TextField(blank=True)  # string
    license_title = models.TextField(blank=True)  # string

    describedby_href = models.URLField()  # string
    describedby_rel = models.TextField(default="describedby", editable=False)  # string
    describedby_type = models.TextField(blank=True)  # string
    describedby_title = models.TextField(blank=True)  # string

    # The field formerly know as "providers" has been "sourced out" to a separate
    # Provider class with many-to-many relation to the Collection objects.

    # The field formerly known as "stac_extensions" has been "sourced out" to a
    # separate Extensions class with many-to-many relations to the Collection objects.
    stac_version = models.TextField()  # string
    eo_gsd = models.FloatField(blank=True)

    # geoadmin_variant implemented by separate class Geoadmin_Variant with many
    # to many relations with Collection objects
    # if it is only a few values that are allowed as "geoadmin:variant", then a similar
    # approach as in the class "Provider" could be used instead (function that checks for a few
    # allowed values), rather than defining an extra model class "Geoadmin_Variant"

    proj = models.IntegerField(blank=True)
    title = models.TextField(blank=True)  # string

    # TODO: implement full functionality of the "summaries"-element

    def __str__(self):
        return self.collection_name

    def clean(self):
        if self.SW_elev is None or self.NE_elev is None:
            if not (self.SW_elev is None and self.NE_elev is None):
                raise ValidationError(_(
                    'If intended spatial extent is 3D, then elevation needs to be defined in southwesterly most and northeasterly most point.'
                ))

        if self.start_date is None and self.end_date is None:
            raise ValidationError(_('At least a start date or an end date has to be defined.'))


class Item(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    # spatial extent (2D ord 3D):
    # bbox: southwesterly most extent followed by all axes of the northeasterly
    # most extent specified in Longitude/Latitude or Longitude/Latitude/Elevation
    # based on WGS 84.
    # Example that covers the whole Earth: [[-180.0, -90.0, 180.0, 90.0]].
    # Example that covers the whole earth with a depth of 100 meters to a height
    # of 150 meters: [[-180.0, -90.0, -100.0, 180.0, 90.0, 150.0]].
    SW_lon = models.FloatField()
    SW_lat = models.FloatField()
    SW_elev = models.FloatField(blank=True)
    NE_lon = models.FloatField()
    NE_lat = models.FloatField()
    NE_elev = models.FloatField(blank=True)

    geometry_coordinates = models.TextField()  # [Float]
    geometry_type = models.TextField()  # string, possible geometry types are:
    # "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", and "GeometryCollection".
    item_name = models.TextField(unique=True, blank=False)

    # link objects
    self_href = models.URLField()  # string
    self_rel = models.TextField(default="self", editable=False)  # string
    self_type = models.TextField(blank=True)  # string
    self_title = models.TextField(blank=True)  # string

    root_href = models.URLField()  # string
    root_rel = models.TextField(default="root", editable=False)  # string
    root_type = models.TextField(blank=True)  # string
    root_title = models.TextField(blank=True)  # string

    parent_href = models.URLField()  # string
    parent_rel = models.TextField(default="parent", editable=False)  # string
    parent_type = models.TextField(blank=True)  # string
    parent_title = models.TextField(blank=True)  # string

    collection_href = models.URLField()  # string
    collection_rel = models.TextField(default="collection", editable=False)  # string
    collection_type = models.TextField(blank=True)  # string
    collection_title = models.TextField(blank=True)  # string

    properties = models.JSONField(
        blank=False
    )  # core metadata (e.g. datetime, eo:bands, eo:cloud_cover, eo:gsd, ...) fields plus extensions
    properties_datetime = models.DateTimeField()
    properties_eo_bands = model.TextFields(blank=True)  # ? [string]?
    properties_eo_cloud_cover = models.FloatField(blank=True)  # float
    properties_eo_gds = models.FloatField(blank=True)
    properties_instruments = models.TextField(blank=True)  # [string]
    properties_license = models.TextField(blank=True)  # string
    properties_platform = models.TextField(blank=True)  # string
    # properties_providers is implemented as separate class "Provider_Item" with
    # many-to-many relations to class Item objects
    properties_title = models.TextField(blank=True)  # string
    properties_view_off_nadir = models.FloatField(blank=True)
    properties_view_sun_azimuth = models.FloatField(blank=True)
    properties_view_elevation = models.FloatField(blank=True)

    # field "stac_extension" is implemented via separate class
    # Extension_Item and many-to-many relations to class Item objects.

    stac_version = models.TextField(blank=False)
    GeoJSON_type = models.TextField(default="Feature", blank=False, editable=False)
    # specifies the GeoJSON type and MUST be set to "Feature". Guess there is a more elegant way to prescribe a fixed value
    # other than giving a default value and don't allow editing.
    assets = models.TextField()
    # this is defined as required here: https://github.com/radiantearth/stac-spec/blob/v0.9.0/item-spec/item-spec.md
    # and is meant to contain a dictionary of asset objects than can be downloaded, each with a unique key
    location = models.URLField()

    def __str__(self):
        return self.item_name

    def clean(self):
        if self.SW_elev is None or self.NE_elev is None:
            if not (self.SW_elev is None and self.NE_elev is None):
                raise ValidationError(_(
                    'If intended spatial extent is 3D, then elevation needs to be defined in southwesterly most and northeasterly most point.'
                ))


class Asset(models.Model):
    feature = models.ForeignKey(Item, on_delete=models.CASCADE)
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, blank=True, editable=False)
    id = models.PositiveBigIntegerField(primary_key=True)

    # using BigIntegerField as primary_key to deal with the expected large number of assets.

    # alter save-function, so that the corresponding collection of the parent item of the asset
    # is saved, too.
    def save(self, *args, **kwargs):
        self.collection = self.feature.collection
        super().save(*args, **kwargs)

    # using "_name" instead of "_id", as "_id" has a default meaning in django
    asset_name = models.TextField(unique=True, blank=False)
    checksum_multihash = models.TextField(blank=False)
    description = models.TextField()
    eo_gsd = models.FloatField()

    class Language(models.TextChoices):
        GERMAN = 'de', _('German')
        ITALIAN = 'it', _('Italian')
        FRENCH = 'fr', _('French')
        ROMANSH = 'rm', _('Romansh')
        ENGLISH = 'en', _('English')
        NONE = '', _('')

    geoadmin_lang = models.CharField(max_length=2, choices=Language.choices, default=Language.NONE)
    geoadmin_variant = models.TextField()
    proj = models.IntegerField(null=True)
    title = models.TextField()
    media_type = models.TextField()
    copyFromHref = models.URLField()
    location = models.URLField()

    def __str__(self):
        return self.asset_name


class Keyword(models.Model):
    collections = models.ManyToManyField(Collection)
    keyword = models.TextField(blank=False)  # string


class Provider_Collection(models.Model):
    collections = models.ManyToManyField(Collection)
    name = models.TextField(blank=False)  # string
    description = models.TextField()  # string
    roles = models.TextField()[string]
    # possible roles are licensor, producer, processor or host. Probably it might sense
    url = models.URLField()  # string

    def clean(self):
        allowed_roles = ['licensor', 'producer', 'processor', 'host']
        for role in self.roles:
            if role not in allowed_roles:
                raise ValidationError(_('Incorrectly defined role found'))


class Provider_Item(models.Model):
    items = models.ManyToManyField(Item)
    name = models.TextField(blank=False)  # string
    description = models.TextField()  # string
    roles = models.TextField()[string]
    # possible roles are licensor, producer, processor or host. Probably it might sense
    url = models.URLField()  # string

    def clean(self):
        allowed_roles = ['licensor', 'producer', 'processor', 'host']
        for role in self.roles:
            if role not in allowed_roles:
                raise ValidationError(_('Incorrectly defined role found'))


class Extension_Collection(models.Mode):
    collections = models.ManyToManyField(Collection)
    url = models.URLField(blank=True)
    name = models.TextField(blank=True)

    # idea here is: when ingesting the delivered array of strings, for each element do:
    # check if it is just a "normal" string --> save it to the "name" field, or:
    # if it is a URL --> save it to the "url" field.
    # One of the two fields (name or url) has to be correctly defined.
    # this is checked by the clean() below:

    def clean(self):
        if self.url is None and self.name is None:
            raise ValidationError(_('One of the properties url or name must be correctly defined'))


class Extension_Item(models.Mode):
    collections = models.ManyToManyField(Item)
    url = models.URLField(blank=True)
    name = models.TextField(blank=True)

    # idea here is: when ingesting the delivered array of strings, for each element do:
    # check if it is just a "normal" string --> save it to the "name" field, or:
    # if it is a URL --> save it to the "url" field.
    # One of the two fields (name or url) has to be correctly defined.
    # this is checked by the clean() below:

    def clean(self):
        if self.url is None and self.name is None:
            raise ValidationError(_('One of the properties url or name must be correctly defined'))


# if it is only a few values that are allowed as "geoadmin:variant", then a similar
# approach as in the class "Provider" could be used instead (function that checks for a few
# allowed values), rather than defining an extra model class "Geoadmin_Variant"
class Geoadmin_Variant(models.Model):
    collections = models.ManyToManyField(Collection)
    name = models.TextField(blank=False)
