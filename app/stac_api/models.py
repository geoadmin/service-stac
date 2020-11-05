import logging
import re

import numpy as np

from django.contrib.gis.db import models
from django.contrib.gis.geos import Polygon
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.translation import gettext_lazy as _

# pylint: disable=fixme
# TODO remove this pylint disable once this is done

logger = logging.getLogger(__name__)

# We use the WGS84 bounding box as defined here:
# https://epsg.io/2056
_BBOX_CH = Polygon.from_bbox((5.96, 45.82, 10.49, 47.81))
_BBOX_CH.srid = 4326
# equal to
# 'SRID=4326;POLYGON ((5.96 45.82, 5.96 47.81, 10.49 47.81, 10.49 45.82, 5.96 45.82))'
BBOX_CH = str(_BBOX_CH)

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

DEFAULT_EXTENT_VALUE = {"spatial": {"bbox": [[None]]}, "temporal": {"interval": [[None, None]]}}

DEFAULT_SUMMARIES_VALUE = {"eo:gsd": [], "geoadmin:variant": [], "proj:epsg": []}


def get_default_stac_extensions():
    return list(DEFAULT_STAC_EXTENSIONS.values())


def get_default_extent_value():
    return DEFAULT_EXTENT_VALUE


def get_default_summaries_value():
    return DEFAULT_SUMMARIES_VALUE


def float_in(flt, floats, **kwargs):
    '''
    This function is needed for comparing floats in order to check if a
    given float is member of a list of floats.
    '''
    return np.any(np.isclose(flt, floats, **kwargs))


class Keyword(models.Model):
    name = models.CharField(max_length=64)  # string

    def __str__(self):
        return self.name


class Link(models.Model):
    href = models.URLField()
    rel = models.CharField(max_length=30)
    # added link_ to the fieldname, as "type" is reserved
    link_type = models.CharField(blank=True, null=True, max_length=150)
    title = models.CharField(blank=True, null=True, max_length=255)

    class Meta:
        abstract = True

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
        if self.roles is None:
            # Note this can happen from the admin page where we need to add the roles as comma
            # separated and not as a python list e.g.
            # `["licensor", "producer"]` => gives self.roles == None
            raise ValidationError(_('Invalid role'))
        allowed_roles = ['licensor', 'producer', 'processor', 'host']
        for role in self.roles:
            if role not in allowed_roles:
                raise ValidationError(_('Invalid role'))


# For Collections and Items: No primary key will be defined, so that the auto-generated ones
# will be used by Django. For assets, a primary key is defined as "BigAutoField" due the
# expected large number of assets


class Collection(models.Model):
    created = models.DateTimeField(auto_now_add=True)  # datetime
    updated = models.DateTimeField(auto_now=True)  # datetime
    description = models.TextField()  # string  / intentionally TextField and
    extent_geometry = models.PolygonField(default=None, srid=4326, editable=True, null=True)
    # not CharField to provide more space for the text.
    # TODO: ""description" is required in radiantearth spec, not required in our spec
    # temporal extent will be auto-populated on every item update inside this collection:
    # start_date will be set to oldest date, end_date to most current date
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
    # extent = models.JSONField(
    #    default=get_default_extent_value, encoder=DjangoJSONEncoder, editable=False
    # )
    start_date = models.DateTimeField(editable=False, null=True, blank=True)
    end_date = models.DateTimeField(editable=False, null=True, blank=True)
    # the bbox field below has no meaning yet and was only introduced for testing
    # while working on the temporal extent.
    bbox = ArrayField(
        ArrayField(models.FloatField(null=True, blank=True), null=True, blank=True),
        null=True,
        blank=True,
        editable=False
    )
    collection_name = models.CharField(unique=True, max_length=255)  # string
    # collection_name is what is simply only called "id" in here:
    # http://ltboc.infra.bgdi.ch/static/products/data.geo.admin.ch/apitransactional.html#operation/createCollection

    keywords = models.ManyToManyField(Keyword)
    license = models.CharField(max_length=30)  # string
    providers = models.ManyToManyField(Provider)

    # "summaries" values will be updated on every update of an asset inside the
    # collection
    summaries = models.JSONField(
        default=get_default_summaries_value, encoder=DjangoJSONEncoder, editable=False
    )
    title = models.CharField(blank=True, max_length=255)  # string

    def __str__(self):
        return self.collection_name

    def update_geoadmin_variants(self, asset_geoadmin_variant, asset_proj_epsg, asset_eo_gsd):
        '''
        updates the collection's summaries when assets are updated or raises
        errors when this fails.
        :param asset_geoadmin_value: asset's value for geoadmin_variant
        :param asset_proj_epsg: asset's value for proj:epsg
        :param asset_eo_gsd: asset's value for asset_eo_gsd
        For all the given parameters this function checks, if the corresponding
        parameters of the collection need to be updated. If so, they will be either
        updated or an error will be raised, if updating fails.
        '''
        try:

            # logger.debug(
            #     "updating geoadmin:variants, self.summaries['eo:gsd']=%s, asset_eo_gsd=%s",
            #     self.summaries["geoadmin:variant"],
            #     asset_eo_gsd
            # )

            if asset_geoadmin_variant and \
               asset_geoadmin_variant not in self.summaries["geoadmin:variant"]:
                self.summaries["geoadmin:variant"].append(asset_geoadmin_variant)
                self.save()

            if asset_proj_epsg and asset_proj_epsg not in self.summaries["proj:epsg"]:
                self.summaries["proj:epsg"].append(asset_proj_epsg)
                self.save()

            if asset_eo_gsd and not float_in(asset_eo_gsd, self.summaries["eo:gsd"]):
                self.summaries["eo:gsd"].append(asset_eo_gsd)
                self.save()

        except KeyError as err:
            logger.error(
                "Error when updating collection's summaries values due to asset update: %s", err
            )
            raise ValidationError(_(
                "Error when updating collection's summaries values due to asset update."
            ))

    def update_temporal_extent(self, item_properties_datetime):
        '''
        updates the collection's temporal extent when item's are update.
        :param item_properties_datetime: item's value for properties_datetime.
        This function checks, if the corresponding parameter of the collection
        needs to be updated. If so, it will be either updated or an error will
        be raised, if updating fails.
        '''
        try:

            if self.start_date is None:
                self.start_date = item_properties_datetime
                self.save()
            elif item_properties_datetime < self.start_date:
                self.start_date = item_properties_datetime
                self.save()
            elif self.end_date is None:
                self.end_date = item_properties_datetime
                self.save()
            elif item_properties_datetime > self.end_date:
                self.end_date = item_properties_datetime
                self.save()
            # TODO: Delete-case!

        except (KeyError, IndexError) as err:

            logger.error('Updating the collection extent due to item update failed: %s', err)
            raise ValidationError(_("Updating the collection extent due to item update failed."))

    def update_bbox_extent(self, action, item_geom, item_id):
        '''
        updates the collection's spatial extent when an item is updated.
        :param action: eighter up (insert, update) or rm (delete)
        :param geometry: the geometry of the item
        :param item_id the id of the item being treated
        This function generates a new extent regarding all the items with the same
        collection foreign key. If there is no spatial bbox yet, the one of the geometry of the
        item is being used.
        '''

        # insert (as item_id is None)
        if action == 'up' and item_id is None:
            # the first item of this collection
            if self.extent_geometry is None:
                self.extent_geometry = Polygon.from_bbox(GEOSGeometry(item_geom).extent)
            # there is already a geometry in the collection a union of the geometries
            else:
                self.extent_geometry = Polygon.from_bbox(
                    GEOSGeometry(self.extent_geometry).union(GEOSGeometry(item_geom)).extent
                )

        # update
        if action == 'up' and item_id:
            # is the new bbox larger than (and covering) the existing
            if Polygon.from_bbox(GEOSGeometry(item_geom).extent).covers(self.extent_geometry):
                self.extent_geometry = Polygon.from_bbox(GEOSGeometry(item_geom).extent)
            # we need to iterat trough the items
            else:
                qs = Item.objects.filter(collection_id=self.pk).exclude(id=item_id)
                union_geometry = GEOSGeometry(item_geom)
                for item in qs:
                    union_geometry = union_geometry.union(item.geometry)
                self.extent_geometry = Polygon.from_bbox(union_geometry.extent)

        # delete, we need to iterate trough the items
        if action == 'rm':
            qs = Item.objects.filter(collection_id=self.pk).exclude(id=item_id)
            union_geometry = GEOSGeometry('Multipolygon EMPTY')
            for item in qs:
                union_geometry = union_geometry.union(item.geometry)
            self.extent_geometry = Polygon.from_bbox(union_geometry.extent)

        self.save()

    def clean(self):
        # very simple validation, raises error when geoadmin_variant strings contain special
        # characters or umlaut.

        for variant in self.summaries["geoadmin:variant"]:
            if not bool(re.search('^[a-zA-Z0-9]*$', variant)):
                logger.error(
                    "Property geoadmin:variant not compatible with the naming conventions."
                )
                raise ValidationError(_("Property geoadmin:variant not compatible with the"
                                        "naming conventions."))


class CollectionLink(Link):
    collection = models.ForeignKey(
        Collection, related_name='links', related_query_name='link', on_delete=models.CASCADE
    )

    class Meta:
        unique_together = (('rel', 'collection'),)


class Item(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    geometry = models.PolygonField(default=BBOX_CH, srid=4326)
    item_name = models.CharField(unique=True, blank=False, max_length=255)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # after discussion with Chris and Tobias: for the moment only support
    # proterties: datetime, eo_gsd and title (the rest is hence commented out)
    properties_datetime = models.DateTimeField()
    # properties_eo_bands = model.TextFields(blank=True)  # ? [string]?
    # properties_eo_cloud_cover = models.FloatField(blank=True)
    # eo_gsd is defined on asset level and will be updated here on ever
    # update of an asset inside this item.
    properties_eo_gsd = ArrayField(models.FloatField(), blank=True, null=True, editable=False)
    # TODO: Not sure, if properties_eo_gsd really needs to be a list, or if it is
    # just one single value per item.
    # properties_instruments = models.TextField(blank=True)
    # properties_license = models.TextField(blank=True)
    # properties_platform = models.TextField(blank=True)
    # properties_providers = models.ManyToManyField(Provider)
    properties_title = models.CharField(blank=True, max_length=255)

    # properties_view_off_nadir = models.FloatField(blank=True)
    # properties_view_sun_azimuth = models.FloatField(blank=True)
    # properties_view_elevation = models.FloatField(blank=True)

    def __str__(self):
        return self.item_name

    def update_properties_eo_gsd(self, asset_eo_gsd):
        '''
        updates the item's properties_eo_gsd when assets are updated or
        raises errors when this fails
        :param asset_eo_gsd: asset's value for asset_eo_gsd

        This function checks, if the item's properties_eo_gds property
        needs to be updated. If so, it will be either
        updated or an error will be raised, if updating fails.
        '''
        # check if eo:gsd on feature/item level needs updates
        if self.properties_eo_gsd is None:
            self.properties_eo_gsd = [asset_eo_gsd]
            self.save()
        elif not float_in(asset_eo_gsd, self.properties_eo_gsd):
            self.properties_eo_gsd.append(asset_eo_gsd)
            self.save()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        # TODO: check if collection's bbox needs to be updated
        # --> this could probably best be done with GeoDjango? (@Tobias)
        # I leave this open for the moment.
        self.collection.update_temporal_extent(self.properties_datetime)

        self.collection.update_bbox_extent('up', self.geometry, self.pk)

        super().save(force_insert, force_update, using, update_fields)

    def delete(self, using=None, keep_parents=False):
        self.collection.update_bbox_extent('rm', self.geometry, self.pk)
        super().delete()


class ItemLink(Link):
    item = models.ForeignKey(
        Item, related_name='links', related_query_name='link', on_delete=models.CASCADE
    )


class Asset(models.Model):
    # using BigIntegerField as primary_key to deal with the expected large number of assets.
    id = models.BigAutoField(primary_key=True)
    item = models.ForeignKey(
        Item, related_name='assets', related_query_name='asset', on_delete=models.CASCADE
    )
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, blank=True, editable=False)

    # using "_name" instead of "_id", as "_id" has a default meaning in django
    asset_name = models.CharField(unique=True, blank=False, max_length=255)
    checksum_multihash = models.CharField(blank=False, max_length=255)
    description = models.TextField()
    eo_gsd = models.FloatField(null=True)

    class Language(models.TextChoices):
        # pylint: disable=invalid-name
        GERMAN = 'de', _('German')
        ITALIAN = 'it', _('Italian')
        FRENCH = 'fr', _('French')
        ROMANSH = 'rm', _('Romansh')
        ENGLISH = 'en', _('English')
        NONE = '', _('')

    geoadmin_lang = models.CharField(
        max_length=2, choices=Language.choices, default=Language.NONE, null=True
    )
    # after discussion with Chris and Tobias: geoadmin_variant will be an
    # array field of CharFields. Simple validation is done (e.g. no "Sonderzeichen"
    # in array)
    geoadmin_variant = models.CharField(max_length=15, null=True, blank=True)
    proj_epsg = models.IntegerField(null=True)
    title = models.CharField(max_length=255)
    media_type = models.CharField(max_length=200)
    href = models.URLField(max_length=255)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.asset_name

    def clean(self):
        # very simple validation, raises error when geoadmin_variant strings contain special
        # characters or umlaut.
        if not bool(re.search('^[a-zA-Z0-9]*$', self.geoadmin_variant)):
            logger.error("Property geoadmin:variant not compatible with the naming conventions.")
            raise ValidationError(_("Property geoadmin:variant not compatible with the "
                                    "naming conventions."))

    # alter save-function, so that the corresponding collection of the parent item of the asset
    # is saved, too.
    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):

        self.item.collection.update_geoadmin_variants(
            self.geoadmin_variant, self.proj_epsg, self.eo_gsd
        )
        if self.eo_gsd:
            self.item.update_properties_eo_gsd(self.eo_gsd)

        super().save(force_insert, force_update, using, update_fields)
