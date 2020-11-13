import logging
import re

import numpy as np

from django.contrib.gis.db import models
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Polygon
from django.contrib.gis.geos.error import GEOSException
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


def validate_link_rel(value):
    invalid_rel = ['self', 'root', 'parent', 'items', 'collection']
    if value in invalid_rel:
        raise ValidationError(_(f'Invalid rel attribute, must not be in {invalid_rel}'))


def validate_geometry(geometry):
    '''
    A validator function that ensures, that only valid
    geometries are stored.
    param: geometry
    '''
    geos_geometry = GEOSGeometry(geometry)
    if geos_geometry.empty:
        message = "The geometry is empty: %s" % geos_geometry.wkt
        logger.error(message)
        raise ValidationError(_(message))
    if not geos_geometry.valid:
        message = "The geometry is not valid: %s" % geos_geometry.valid_reason
        logger.error(message)
        raise ValidationError(_(message))
    return geometry


class Link(models.Model):
    href = models.URLField()
    rel = models.CharField(max_length=30, validators=[validate_link_rel])
    # added link_ to the fieldname, as "type" is reserved
    link_type = models.CharField(blank=True, null=True, max_length=150)
    title = models.CharField(blank=True, null=True, max_length=255)

    class Meta:
        abstract = True

    def __str__(self):
        return '%s: %s' % (self.rel, self.href)


class Provider(models.Model):
    collection = models.ForeignKey(
        'stac_api.Collection',
        on_delete=models.CASCADE,
        related_name='providers',
        related_query_name='provider'
    )
    name = models.CharField(blank=False, max_length=200)
    description = models.TextField(blank=True, null=True)
    # possible roles are licensor, producer, processor or host
    allowed_roles = ['licensor', 'producer', 'processor', 'host']
    roles = ArrayField(models.CharField(max_length=9), help_text=_(
        "Comma-separated list of roles. Possible values are {}".format(
            ', '.join(allowed_roles)))
                      )
    url = models.URLField()

    class Meta:
        unique_together = (('collection', 'name'),)

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
            if role not in self.allowed_roles:
                raise ValidationError(_('Invalid role'))


# For Collections and Items: No primary key will be defined, so that the auto-generated ones
# will be used by Django. For assets, a primary key is defined as "BigAutoField" due the
# expected large number of assets


class Collection(models.Model):
    created = models.DateTimeField(auto_now_add=True)  # datetime
    updated = models.DateTimeField(auto_now=True)  # datetime
    description = models.TextField()  # string  / intentionally TextField and
    extent_geometry = models.PolygonField(
        default=None,
        srid=4326,
        editable=False,
        blank=True,
        null=True,
        validators=[validate_geometry]
    )
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
    cache_start_datetime = models.DateTimeField(editable=False, null=True, blank=True)
    cache_end_datetime = models.DateTimeField(editable=False, null=True, blank=True)
    collection_name = models.CharField(unique=True, max_length=255)  # string
    # collection_name is what is simply only called "id" in here:
    # http://ltboc.infra.bgdi.ch/static/products/data.geo.admin.ch/apitransactional.html#operation/createCollection

    license = models.CharField(max_length=30)  # string

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

    def update_temporal_extent( # pylint: disable=too-many-branches, too-many-statements)
        self,
        action,
        old_start_datetime,
        new_start_datetime,
        old_end_datetime,
        new_end_datetime,
        item_id
    ):
        '''
        updates the collection's temporal extent when item's are updated. This
        function will only be called, if the item's properties start_ or end_
        datetime or the properties_datetime have changed (at least one of them).
        :param action: either up (insert, update) or rm (delete)
        :param old_start_datetime: item's old value for properties_start_datetime
        :param new_start_datetime: item's updated value for properties_start_datetime
        :param old_end_datetime: item's old value for properties_end_datetime
        :param new_end_datetime: item's updated value for properties_end_datetime
        :param item_id the id of the item being treated
        If the calling item has no range defined (i.e. no properties.start_datetime
        and no properties.end_datetime, but a properties.datetime only), this
        function will be called using the item's properties.datetime both for the
        start_ and the end_datetime as well.
        If updating the collection's temporal extent fails, an error will be raised.
        '''

        def insert_new_item():
            logger.debug('Inserting item %s in collection %s', item_id, self.collection_name)
            if self.cache_start_datetime is None:
                # first item in collection, as cache_start_datetime is None:
                self.cache_start_datetime = new_start_datetime
            elif self.cache_start_datetime > new_start_datetime:
                # new item starts earlier that current collection range starts
                self.cache_start_datetime = new_start_datetime

            if self.cache_end_datetime is None:
                #first item in collection, as cache_start_datetime is None
                self.cache_end_datetime = new_end_datetime
            elif self.cache_end_datetime < new_end_datetime:
                # new item starts after current collection's range ends
                self.cache_end_datetime = new_end_datetime

            self.save()

        def update_item():
            logger.debug('Updating item %s in collection %s', item_id, self.collection_name)
            if old_start_datetime != new_start_datetime:
                # start_datetime was updated
                if old_start_datetime == self.cache_start_datetime:
                    # item's old start_datetime was defining left bound of the temporal
                    # extent interval of collection before update
                    if new_start_datetime < old_start_datetime:
                        # item's start_datetime was shifted to the left (earlier)
                        self.cache_start_datetime = new_start_datetime
                    else:
                        # item's start_datetime was shifted to the right (later)
                        # but was defining the left bound of the temporal extent
                        # of the collection before
                        # --> hence the new start_datetime of the collection
                        # needs to be determinded:
                        # get all items but the one to that is beeing updated:
                        logger.warning(
                            'Looping (twice) over all items of collection %s,'
                            'to update temporal extent, this may take a while',
                            self.collection_name
                        )
                        qs = Item.objects.filter(collection_id=self.pk).exclude(id=item_id)
                        # get earliest start_datetime or none, in case none exists
                        # this should be the case, if the item that is currently
                        # beeing updated is the only item in the collection or
                        # no item has a range defined (no start_ and end_datetimes)
                        # but all do only have properties.datetimes defined.
                        if qs.filter(properties_start_datetime__isnull=False):
                            earliest_start_datetime = qs.filter(
                                properties_start_datetime__isnull=False
                            ).earliest('properties_start_datetime').properties_start_datetime
                        else:
                            earliest_start_datetime = None

                        # get earliest datetime, or none in case none exists
                        # this should be the case, if the item that is currently
                        # beeing updated is the only item in the collection or
                        # no item has properties.datetime defined but all do have
                        # only ranged (start_ and end_datetimes defined)
                        if qs.filter(properties_datetime__isnull=False):
                            earliest_datetime = qs.filter(
                                properties_datetime__isnull=False
                            ).earliest('properties_datetime').properties_datetime
                        else:
                            earliest_datetime = None

                        if earliest_start_datetime is None and earliest_datetime is None:
                            # currently updated item is the only one:
                            self.cache_start_datetime = new_start_datetime
                        elif earliest_start_datetime is not None:
                            self.cache_start_datetime = earliest_start_datetime
                        else:
                            self.cache_start_datetime = earliest_datetime
                elif new_start_datetime < self.cache_start_datetime:
                    # item's start_datetime did not define the left bound of the
                    # collection's temporal extent before update, which does not
                    # matter anyways, as it defines the new left bound after update
                    # and collection's start_datetime can be simply adjusted
                    self.cache_start_datetime = new_start_datetime

            if old_end_datetime != new_end_datetime:
                # end_datetime was updated
                if old_end_datetime == self.cache_end_datetime:
                    # item's old end_datetime was defining the right bound of
                    # the collection's temporal extent interval before update
                    if new_end_datetime > old_end_datetime:
                        # item's end_datetime was shifted to the right (later)
                        self.cache_end_datetime = new_end_datetime
                    else:
                        # item's end_datetime was shifted to the left (earlier)
                        # but was defining the right bound of the collection's
                        # temporal extent.
                        # --> hence the new end_datetime of the collection needs
                        # to be determined

                        # get all items but the one to that is beeing updated:
                        logger.warning(
                            'Looping (twice) over all items of collection %s,'
                            'to update temporal extent, this may take a while',
                            self.collection_name
                        )
                        qs = Item.objects.filter(collection_id=self.pk).exclude(id=item_id)
                        # get latest end_datetime or none, in case none exists
                        # this should be the case, if the item that is currently
                        # beeing updated is the only item in the collection or
                        # no item has a range defined (no start_ and end_datetimes)
                        # but all do only have properties.datetimes defined.
                        if qs.filter(properties_end_datetime__isnull=False):
                            latest_end_datetime = qs.filter(
                                properties_end_datetime__isnull=False
                            ).latest('properties_end_datetime').properties_end_datetime
                        else:
                            latest_end_datetime = None

                        # get latest datetime, or none in case none exists
                        # this should be the case, if the item that is currently
                        # beeing updated is the only item in the collection or
                        # no item has properties.datetime defined but all do have
                        # only ranged (start_ and end_datetimes defined)
                        if qs.filter(properties_datetime__isnull=False):
                            latest_datetime = qs.filter(
                                properties_datetime__isnull=False
                            ).latest('properties_datetime').properties_datetime
                        else:
                            latest_datetime = None

                        if latest_end_datetime is None and latest_datetime is None:
                            # currently updated item is the only one:
                            self.cache_end_datetime = new_end_datetime
                        elif latest_end_datetime is not None:
                            self.cache_end_datetime = latest_end_datetime
                        else:
                            self.cache_end_datetime = latest_datetime
                elif new_end_datetime > self.cache_start_datetime:
                    # item's end_datetime did not define the right bound of
                    # the collection's temporal extent before update, which
                    # does not matter anyways, as it defines the right bound
                    # after update and collection's end_date can be simply
                    # adjusted
                    self.cache_end_datetime = new_end_datetime

            self.save()

        def delete_item():
            logger.debug('Deleting item %s from collection %s', item_id, self.collection_name)

            if old_start_datetime == self.cache_start_datetime or \
                old_end_datetime == self.cache_end_datetime:
                logger.warning(
                    'Looping over all items of collection %s,'
                    'to update temporal extent, this may take a while',
                    self.collection_name
                )
                # get all items but the one to be deleted:
                qs = Item.objects.filter(collection_id=self.pk).exclude(id=item_id)

            if old_start_datetime == self.cache_start_datetime:
                # item that is to be deleted defined left bound of collection's
                # temporal extent
                # first set cache_start_datetime to None, in case
                # the currently deleted item is the only item of the collection
                self.cache_start_datetime = None

                logger.warning(
                    'Looping (twice) over all items of collection %s,'
                    'to update temporal extent, this may take a while',
                    self.collection_name
                )

                # get earliest start_datetime or none, in case none exists
                if qs.filter(properties_start_datetime__isnull=False):
                    earliest_start_datetime = qs.filter(
                        properties_start_datetime__isnull=False
                    ).earliest('properties_start_datetime').properties_start_datetime
                else:
                    earliest_start_datetime = None

                # get earliest datetime, or none in case none exists
                if qs.filter(properties_datetime__isnull=False):
                    earliest_datetime = qs.filter(
                        properties_datetime__isnull=False
                    ).earliest('properties_datetime').properties_datetime
                else:
                    earliest_datetime = None

                # set collection's new start_datetime to the minimum of the earliest
                # item's start_datetime or datetime
                if earliest_start_datetime is not None and earliest_datetime is not None:
                    self.cache_start_datetime = min(earliest_start_datetime, earliest_datetime)
                elif earliest_datetime is not None:
                    self.cache_start_datetime = earliest_datetime
                else:
                    self.cache_start_datetime = earliest_start_datetime

            if old_end_datetime == self.cache_end_datetime:
                # item that is to be deleted defined right bound of collection's
                # temporal extent
                # first set cache_end_datetime to None, in case
                # the currently deleted item is the only item of the collection
                self.cache_end_datetime = None

                logger.warning(
                    'Looping (twice) over all items of collection %s,'
                    'to update temporal extent, this may take a while',
                    self.collection_name
                )
                # get latest end_datetime or none, in case none exists
                if qs.filter(properties_end_datetime__isnull=False):
                    latest_end_datetime = qs.filter(
                        properties_end_datetime__isnull=False
                    ).latest('properties_end_datetime').properties_end_datetime
                else:
                    latest_end_datetime = None

                # get latest datetime, or none in case none exists
                if qs.filter(properties_datetime__isnull=False):
                    latest_datetime = qs.filter(properties_datetime__isnull=False
                                               ).latest('properties_datetime').properties_datetime
                else:
                    latest_datetime = None

                # set collection's new end_datetime to the maximum of the latest
                # item's end_datetime or datetime
                if latest_end_datetime is not None and latest_datetime is not None:
                    self.cache_end_datetime = max(latest_end_datetime, latest_datetime)
                elif latest_datetime is not None:
                    self.cache_end_datetime = latest_datetime
                else:
                    self.cache_end_datetime = latest_end_datetime

            self.save()

        # INSERT (as item_id is None)
        if action == "up" and item_id is None:
            insert_new_item()
        # UPDATE
        elif action == "up" and item_id:
            update_item()
        # DELETE
        elif action == 'rm':
            delete_item()

    def update_bbox_extent(self, action, item_geom, item_id, item_name):
        '''
        updates the collection's spatial extent when an item is updated.
        :param action: either up (insert, update) or rm (delete)
        :param geometry: the geometry of the item
        :param item_id the id of the item being treated
        This function generates a new extent regarding all the items with the same
        collection foreign key. If there is no spatial bbox yet, the one of the geometry of the
        item is being used.
        '''

        try:
            # insert (as item_id is None)
            if action == 'insert':
                logger.debug('Updating collections extent_geometry' ' as a item has been inserted')
                # the first item of this collection
                if self.extent_geometry is None:
                    self.extent_geometry = Polygon.from_bbox(GEOSGeometry(item_geom).extent)
                # there is already a geometry in the collection a union of the geometries
                else:
                    self.extent_geometry = Polygon.from_bbox(
                        GEOSGeometry(self.extent_geometry).union(GEOSGeometry(item_geom)).extent
                    )

            # update
            if action == 'update':
                logger.debug(
                    'Updating collections extent_geometry'
                    ' as a item geometry has been updated'
                )
                # is the new bbox larger than (and covering) the existing
                if Polygon.from_bbox(GEOSGeometry(item_geom).extent).covers(self.extent_geometry):
                    self.extent_geometry = Polygon.from_bbox(GEOSGeometry(item_geom).extent)
                # we need to iterate trough the items
                else:
                    logger.warning(
                        'Looping over all items of collection %s,'
                        'to update extent_geometry, this may take a while',
                        self.pk
                    )
                    qs = Item.objects.filter(collection_id=self.pk).exclude(id=item_id)
                    union_geometry = GEOSGeometry(item_geom)
                    for item in qs:
                        union_geometry = union_geometry.union(item.geometry)
                    self.extent_geometry = Polygon.from_bbox(union_geometry.extent)

            # delete, we need to iterate trough the items
            if action == 'rm':
                logger.debug('Updating collections extent_geometry' ' as a item has been deleted')
                logger.warning(
                    'Looping over all items of collection %s,'
                    'to update extent_geometry, this may take a while',
                    self.pk
                )
                qs = Item.objects.filter(collection_id=self.pk).exclude(id=item_id)
                union_geometry = GEOSGeometry('Polygon EMPTY')
                if bool(qs):
                    for item in qs:
                        union_geometry = union_geometry.union(item.geometry)
                    self.extent_geometry = Polygon.from_bbox(union_geometry.extent)
                else:
                    self.extent_geometry = None
        except GEOSException as error:
            logger.error(
                'Failed to update spatial extend in collection %s with item %s action=%s: %s',
                self.collection_name,
                item_name,
                action,
                error
            )
            raise GEOSException(
                f'Failed to update spatial extend in colletion {self.collection_name} with item '
                f'{item_name}: {error}'
            )

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
    geometry = models.PolygonField(
        null=False, blank=False, default=BBOX_CH, srid=4326, validators=[validate_geometry]
    )
    item_name = models.CharField(unique=True, blank=False, max_length=255)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # after discussion with Chris and Tobias: for the moment only support
    # proterties: datetime, eo_gsd and title (the rest is hence commented out)
    properties_datetime = models.DateTimeField(blank=True, null=True)
    properties_start_datetime = models.DateTimeField(blank=True, null=True)
    properties_end_datetime = models.DateTimeField(blank=True, null=True)
    # properties_eo_bands = model.TextFields(blank=True)  # ? [string]?
    # properties_eo_cloud_cover = models.FloatField(blank=True)
    # eo_gsd is defined on asset level and will be updated here on ever
    # update of an asset inside this item.
    properties_eo_gsd = models.FloatField(blank=True, null=True, editable=False)
    # properties_instruments = models.TextField(blank=True)
    # properties_license = models.TextField(blank=True)
    # properties_platform = models.TextField(blank=True)
    # properties_providers = models.ManyToManyField(Provider)
    properties_title = models.CharField(blank=True, max_length=255)

    # properties_view_off_nadir = models.FloatField(blank=True)
    # properties_view_sun_azimuth = models.FloatField(blank=True)
    # properties_view_elevation = models.FloatField(blank=True)

    # getting the original geometry helps that the bbox of the collection is only
    # when the geometry has changed (during update)
    # https://stackoverflow.com/questions/1355150/when-saving-how-can-you-check-if-a-field-has-changed
    _original_geometry = None
    __original_properties_start_datetime = None
    __original_properties_end_datetime = None
    __original_properties_datetime = None

    def __init__(self, *args, **kwargs):
        super(Item, self).__init__(*args, **kwargs)
        self._original_geometry = self.geometry
        self.__original_properties_start_datetime = self.properties_start_datetime
        self.__original_properties_end_datetime = self.properties_end_datetime
        self.__original_properties_datetime = self.properties_datetime

    def __str__(self):
        return self.item_name

    def clean(self):
        self.validate_datetime_properties()

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        # Make sure that the properties datetime are valid before updating the temporal extent
        # This is needed because save() is called during the Item.object.create() function without
        # calling clean() ! and our validation is done within clean() method.
        self.validate_datetime_properties()

        if self.properties_datetime is not None:
            if self.__original_properties_datetime is not None:
                # This is the case, when the value of properties.datetime has been
                # updated
                self.collection.update_temporal_extent(
                    'up',
                    self.__original_properties_datetime,
                    self.properties_datetime,
                    self.__original_properties_datetime,
                    self.properties_datetime,
                    self.pk
                )
            elif self.__original_properties_datetime is None:
                # This is the case, when the item was defined by a start_ and
                # end_datetime before and has been changed to only have a single
                # datetime property. In that case, we hand over the old
                # start_ and end_datetime values to the update function, so
                # that a loop over all items will only be done, if really
                # necessary.
                self.collection.update_temporal_extent(
                    'up',
                    self.__original_properties_start_datetime,
                    self.properties_datetime,
                    self.__original_properties_end_datetime,
                    self.properties_datetime,
                    self.pk
                )

        elif self.__original_properties_start_datetime is not None and \
            self.__original_properties_end_datetime is not None:
            # This is the case, if an items values for start_ and/or end_datetime
            # were updated.
            self.collection.update_temporal_extent(
                'up',
                self.__original_properties_start_datetime,
                self.properties_start_datetime,
                self.__original_properties_end_datetime,
                self.properties_end_datetime,
                self.pk
            )
        else:
            # This is the case, when an item was defined by a single datetime
            # before and has been changed to contain a start_ and an
            # end_datetime value now.
            self.collection.update_temporal_extent(
                'up',
                self.__original_properties_datetime,
                self.properties_start_datetime,
                self.__original_properties_datetime,
                self.properties_end_datetime,
                self.pk
            )

        # adding a new item means updating the bbox of the collection
        if self.pk is None:
            self.collection.update_bbox_extent('insert', self.geometry, self.pk, self.item_name)
        # update the bbox of the collection only when the geometry of the item has changed
        elif self.geometry != self._original_geometry:
            self.collection.update_bbox_extent('update', self.geometry, self.pk, self.item_name)

        super().save(*args, **kwargs)

        self._original_geometry = self.geometry
        self.__original_properties_start_datetime = self.properties_start_datetime
        self.__original_properties_end_datetime = self.properties_end_datetime
        self.__original_properties_datetime = self.properties_datetime

    def delete(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        if self.properties_datetime is not None:
            self.collection.update_temporal_extent(
                'rm',
                self.__original_properties_datetime,
                self.properties_datetime,
                self.__original_properties_datetime,
                self.properties_datetime,
                self.pk
            )
        else:
            self.collection.update_temporal_extent(
                'rm',
                self.__original_properties_start_datetime,
                self.properties_start_datetime,
                self.__original_properties_end_datetime,
                self.properties_end_datetime,
                self.pk
            )

        self.collection.update_bbox_extent('rm', self.geometry, self.pk, self.item_name)
        super().delete(*args, **kwargs)

    def validate_datetime_properties(self):
        if self.properties_datetime is not None:
            if self.properties_start_datetime is not None \
                or self.properties_end_datetime is not None:
                message = 'Cannot provide together property datetime with datetime range ' \
                    '(start_datetime, end_datetime)'
                logger.error(message)
                raise ValidationError(_(message))
        else:
            if self.properties_end_datetime is None:
                message = "Property end_datetime can't be null when no property datetime is given"
                logger.error(message)
                raise ValidationError(_(message))
            if self.properties_start_datetime is None:
                message = "Property start_datetime can't be null when no property datetime is given"
                logger.error(message)
                raise ValidationError(_(message))

    def update_properties_eo_gsd(self, asset, deleted=False):
        '''
        updates the item's properties_eo_gsd when assets are updated or
        raises errors when this fails
        :param asset: asset's that has been updated/added/deleted
        :param deleted: asset has been deleted

        This function checks, if the item's properties_eo_gds property
        needs to be updated. If so, it will be either
        updated or an error will be raised, if updating fails.
        '''
        # check if eo:gsd on feature/item level needs updates
        if deleted and self.properties_eo_gsd == asset.eo_gsd:
            # querying all object in a save operation is for performance reason not a good idea
            # but here because it first only occur during deleting asset which is a rare case
            # and because we should not have too many assets within an item (a dozen),
            # it is acceptable
            assets = Asset.objects.filter(item__item_name=self.item_name).exclude(id=asset.id)
            self.properties_eo_gsd = min([
                asset.eo_gsd for asset in assets if asset.eo_gsd is not None
            ])
            self.save()
        elif not deleted and self.properties_eo_gsd is None:
            self.properties_eo_gsd = asset.eo_gsd
            self.save()
        elif not deleted and asset.eo_gsd < self.properties_eo_gsd:
            self.properties_eo_gsd = asset.eo_gsd
            self.save()


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
    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        self.item.collection.update_geoadmin_variants(
            self.geoadmin_variant, self.proj_epsg, self.eo_gsd
        )
        if self.eo_gsd is not None:
            self.item.update_properties_eo_gsd(self)

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        if self.eo_gsd is not None:
            self.item.update_properties_eo_gsd(self, deleted=True)
        super().delete(*args, **kwargs)
