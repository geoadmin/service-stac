import re
from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import ArrayField

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
    description = models.TextField()  # string  / intentionally TextField and
    # not CharField to provide more space for the text.
    # TODO: ""description" is required in radiantearth spec, not required in our spec

    # temporal extent will be auto-populated on every item update inside this collection:
    # start_date will be set to oldest date, end_date to most current date
    start_date = models.DateTimeField(blank=True)  # will be automatically populated
    end_date = models.DateTimeField(blank=True)  # will be automatically populated

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
    southwest = ArrayField(models.FloatField(), blank=True)  # [Float], auto-populated
    northeast = ArrayField(models.FloatField(), blank=True)  # [Float], auto-populated

    collection_name = models.CharField(unique=True, default="")  # string
    # collection_name is what is simply only called "id" in here:
    # http://ltboc.infra.bgdi.ch/static/products/data.geo.admin.ch/apitransactional.html#operation/createCollection
    item_type = models.CharField(default="Feature")  # string

    # The field formerly known as "Keywords" has been "sourced out" to a
    # separate Keyword class with many-to-many relations to the Collection objects

    license = models.CharField()  # string

    # link objects are now in separate class Link_Collection with many-to-many
    # relation to Collection objects

    # The field formerly know as "providers" has been "sourced out" to a separate
    # Provider class with many-to-many relation to the Collection objects.

    # after discussion with Chris and Tobias:
    # stac_extension will be populated with default values that are set to be
    # non-editable for the moment. Could be changed, should the need arise.
    stac_extension = ArrayField(
        models.CharField(),
        default=[
            'eo',
            'proj',
            'view',
            'https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json'
        ],
        editable=False
    )
    stac_version = models.CharField()  # string

    # "summaries" values will be updated on every update of an item inside the
    # collection --> TODO: rewrite items save() function accordingly
    summaries_eo_gsd = models.FloatField(blank=True)
    summaries_proj = ArrayField(models.IntegerField(blank=True))
    # after discussion with Chris and Tobias: geoadmin_variant will be an
    # array field of CharFields. Simple validation is done (e.g. no "Sonderzeichen"
    # in array)
    # TODO: Probably geoadmin_variant could be also auto-populated on every
    # update of an asset --> update the geoadmin_variant of the corresponding
    # collection
    geoadmin_variant = ArrayField(models.CharField())

    title = models.CharField(blank=True)  # string

    def __str__(self):
        return self.collection_name

    def clean(self):
        # TODO: move this check to the items save()
        if self.start_date is None and self.end_date is None:
            raise ValidationError(_('At least a start date or an end date has to be defined.'))

        # very simple validation, raises error when geoadmin_variant strings contain special
        # characters or umlaut.
        for variant in self.geoadmin_variant:
            if not bool(re.search('^[a-zA-Z0-9]*$', variant)):
                raise ValidationError(_('Property geoadmin:variant not correctly specified.'))


class Item(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    # spatial extent (2D ord 3D):
    # bbox: southwesterly most extent followed by all axes of the northeasterly
    # most extent specified in Longitude/Latitude or Longitude/Latitude/Elevation
    # based on WGS 84.
    # Example that covers the whole Earth: [[-180.0, -90.0, 180.0, 90.0]].
    # Example that covers the whole earth with a depth of 100 meters to a height
    # of 150 meters: [[-180.0, -90.0, -100.0, 180.0, 90.0, 150.0]].
    # TODO: use GeoDjango for this:
    southwest = ArrayField(models.FloatField(), blank=True)  # [Float]
    northeast = ArrayField(models.FloatField(), blank=True)  # [Float]

    # TODO: use GeoDjango for this:
    geometry_coordinates = models.TextField()  # [Float]
    geometry_type = models.CharField()  # string, possible geometry types are:
    # "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon",
    # "MultiPolygon", and "GeometryCollection".
    item_name = models.CharField(unique=True, blank=False)

    # link objects are now represented by separate class "Link_Item" with
    # many-to-many relation to Item objects.

    # after discussion with Chris and Tobias: for the moment only support
    # proterties: datetime, eo_gsd and title (the rest is hence commented out)
    properties_datetime = models.DateTimeField()
    # properties_eo_bands = model.TextFields(blank=True)  # ? [string]?
    # properties_eo_cloud_cover = models.FloatField(blank=True)  # float
    properties_eo_gsd = models.FloatField(blank=True)
    # properties_instruments = models.TextField(blank=True)  # [string]
    # properties_license = models.TextField(blank=True)  # string
    # properties_platform = models.TextField(blank=True)  # string
    # properties_providers is implemented as separate class "Provider_Item" with
    # many-to-many relations to class Item objects
    properties_title = models.CharField(blank=True)  # string
    # properties_view_off_nadir = models.FloatField(blank=True)
    # properties_view_sun_azimuth = models.FloatField(blank=True)
    # properties_view_elevation = models.FloatField(blank=True)

    # after discussion with Chris and Tobias:
    # stac_extension will be populated with default values that are set to be
    # non-editable for the moment. Could be changed, should the need arise.
    stac_extension = ArrayField(
        models.CharField(),
        default=[
            'eo',
            'proj',
            'view',
            'https://data.geo.admin.ch/stac/geoadmin-extension/1.0/schema.json'
        ],
        editable=False
    )

    stac_version = models.CharField(blank=False)
    GeoJSON_type = models.CharField(default="Feature", blank=False, editable=False)  # pylint: disable=invalid-name
    # specifies the GeoJSON type and MUST be set to "Feature".
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

    def clean(self):
        if len(self.southwest) != len(self.northeast):  # pylint: disable=no-else-raise
            raise ValidationError(_(
                'If intended spatial extent is 3D, then elevation needs to be' \
                'defined in southwesterly most and northeasterly most point.'
            ))
        # don't understand why pylint complains here. Do I get something wrong?
        # To me this elif makes sense, as it will be executed, when
        # len(self.southwest) == len(self.northeast). So I disables the pylint
        # check for the following line.
        elif (len(self.southwest) != 2) and (len(self.southwest) != 3):
            raise ValidationError(_('Bounding box incorrectly defined.'))

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        #TODO: on every item update:
        # 1. re-calculate the envelope over all bboxes of all items inside this
        #    collection and update the collections' bbox accordingly
        #
        # 2. loop over all items inside the collection and set the "start_date"
        #    of the collection to the oldest date found in item dates. Same for
        #    collections' end_date (set to most recent date found in items)
        #
        # 3. also loop over all items inside the collection and update the
        #    collections' "summaries"-values (not sure if this should be done on
        #    asset level instead. I guess so, as "proj" will be defined on asset
        #     level, whereas gsd is defined on item and asset level...)
        #
        # 4.  loop over all items and update the collections "provider" property
        #     on every item update

        super().save(*args, **kwargs)


class Asset(models.Model):
    feature = models.ForeignKey(Item, on_delete=models.CASCADE)
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, blank=True, editable=False)
    asset_id = models.BigAutoField(primary_key=True)

    # using BigIntegerField as primary_key to deal with the expected large number of assets.

    # alter save-function, so that the corresponding collection of the parent item of the asset
    # is saved, too.
    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        self.collection = self.feature.collection
        super().save(*args, **kwargs)

    # using "_name" instead of "_id", as "_id" has a default meaning in django
    asset_name = models.CharField(unique=True, blank=False)
    checksum_multihash = models.CharField(blank=False)
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
    geoadmin_variant = ArrayField(models.CharField())
    proj = models.IntegerField(null=True)
    title = models.CharField()
    media_type = models.CharField()
    copy_from_href = models.URLField()
    location = models.URLField()

    def __str__(self):
        return self.asset_name

    def clean(self):
        # very simple validation, raises error when geoadmin_variant strings contain special
        # characters or umlaut.
        for variant in self.geoadmin_variant:
            if not bool(re.search('^[a-zA-Z0-9]*$', variant)):
                raise ValidationError(_('Property geoadmin:variant not correctly specified.'))


class Keyword(models.Model):
    collections = models.ManyToManyField(Collection)
    keyword = models.TextField(blank=False)  # string


# TODO: probably provider on collection level could be auto-populated and updated
# on every update of an item inside the collection
class ProviderCollection(models.Model):
    collections = models.ManyToManyField(Collection)
    name = models.TextField(blank=False)  # string
    description = models.TextField()  # string
    roles = models.TextField()  # [string]
    # possible roles are licensor, producer, processor or host. Probably it might sense
    url = models.URLField()  # string

    def clean(self):
        allowed_roles = ['licensor', 'producer', 'processor', 'host']
        for role in self.roles:
            if role not in allowed_roles:
                raise ValidationError(_('Incorrectly defined role found'))


class ProviderItem(models.Model):
    items = models.ManyToManyField(Item)
    name = models.TextField(blank=False)  # string
    description = models.TextField()  # string
    roles = models.TextField()  # [string]
    # possible roles are licensor, producer, processor or host. Probably it might sense
    url = models.URLField()  # string

    def clean(self):
        allowed_roles = ['licensor', 'producer', 'processor', 'host']
        for role in self.roles:
            if role not in allowed_roles:
                raise ValidationError(_('Incorrectly defined role found'))


class LinkCollection(models.Model):
    collections = models.ManyToManyField(Collection)
    href = models.URLField()  # string
    rel = models.CharField()  # string
    link_type = models.CharField(blank=True)  # string
    # added link_ to the fieldname, as "type" is reserved
    title = models.CharField(blank=True)  # string


class LinkItem(models.Model):
    items = models.ManyToManyField(Item)
    href = models.URLField()  # string
    rel = models.CharField()  # string
    link_type = models.CharField(blank=True)  # string
    # added link_ to the fieldname, as "type" is reserved
    title = models.CharField(blank=True)  # string
