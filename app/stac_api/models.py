import logging
import re
from datetime import datetime

from django.contrib.gis.db import models
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Polygon
from django.contrib.gis.geos.error import GEOSException
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.translation import gettext_lazy as _

from solo.models import SingletonModel

from stac_api.collection_summaries import update_summaries
from stac_api.temporal_extent import update_temporal_extent
from stac_api.utils import fromisoformat

logger = logging.getLogger(__name__)

# We use the WGS84 bounding box as defined here:
# https://epsg.io/2056
_BBOX_CH = Polygon.from_bbox((5.96, 45.82, 10.49, 47.81))
_BBOX_CH.srid = 4326
# equal to
# 'SRID=4326;POLYGON ((5.96 45.82, 5.96 47.81, 10.49 47.81, 10.49 45.82, 5.96 45.82))'
BBOX_CH = str(_BBOX_CH)

DEFAULT_EXTENT_VALUE = {"spatial": {"bbox": [[None]]}, "temporal": {"interval": [[None, None]]}}

DEFAULT_SUMMARIES_VALUE = {"eo:gsd": [], "geoadmin:variant": [], "proj:epsg": []}


def get_default_extent_value():
    return DEFAULT_EXTENT_VALUE


def get_default_summaries_value():
    return DEFAULT_SUMMARIES_VALUE


def validate_name(name):
    '''Validate name used in URL
    '''
    if not re.match(r'^[0-9a-z-_.]+$', name):
        logger.error('Invalid name %s, only the following characters are allowed: 0-9a-z-_.', name)
        raise ValidationError(
            _('Invalid name, only the following characters are allowed: 0-9a-z-_.')
        )


def validate_geoadmin_variant(variant):
    '''Validate geoadmin:variant, it should not have special characters'''
    if not re.match('^[a-zA-Z0-9]+$', variant):
        logger.error(
            "Invalid geoadmin:variant property %s, special characters not allowed", variant
        )
        raise ValidationError(_("Invalid geoadmin:variant, special characters not allowed"))


def validate_link_rel(value):
    invalid_rel = [
        'self',
        'root',
        'parent',
        'items',
        'collection',
        'service-desc',
        'service-doc',
        'search',
        'conformance'
    ]
    if value in invalid_rel:
        logger.error("Link rel attribute %s is not allowed, it is a reserved attribute", value)
        raise ValidationError(_(f'Invalid rel attribute, must not be in {invalid_rel}'))


def validate_geometry(geometry):
    '''
    A validator function that ensures, that only valid
    geometries are stored.
    Args:
         geometry: The geometry that will be validated

    Returns:
        The geometry, when tested valid

    Raises:
        ValidateionError: About that the geometry is not valid
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


def validate_item_properties_datetimes_dependencies(
    properties_datetime, properties_start_datetime, properties_end_datetime
):
    '''
    Validate the dependencies between the Item datetimes properties

	This makes sure that either only the properties.datetime is set or
	both properties.start_datetime and properties.end_datetime

	Raises:
		django.core.exceptions.ValidationError
    '''
    try:
        if not isinstance(properties_datetime, datetime) and properties_datetime is not None:
            properties_datetime = fromisoformat(properties_datetime)
        if (
            not isinstance(properties_start_datetime, datetime) and
            properties_start_datetime is not None
        ):
            properties_start_datetime = fromisoformat(properties_start_datetime)
        if (
            not isinstance(properties_end_datetime, datetime) and
            properties_end_datetime is not None
        ):
            properties_end_datetime = fromisoformat(properties_end_datetime)
    except ValueError as error:
        logger.error("Invalid datetime string %s", error)
        raise ValidationError(f'Invalid datetime string {error}') from error

    if properties_datetime is not None:
        if (properties_start_datetime is not None or properties_end_datetime is not None):
            message = 'Cannot provide together property datetime with datetime range ' \
                '(start_datetime, end_datetime)'
            logger.error(message)
            raise ValidationError(_(message))
    else:
        if properties_end_datetime is None:
            message = "Property end_datetime can't be null when no property datetime is given"
            logger.error(message)
            raise ValidationError(_(message))
        if properties_start_datetime is None:
            message = "Property start_datetime can't be null when no property datetime is given"
            logger.error(message)
            raise ValidationError(_(message))

    if properties_datetime is None:
        if properties_end_datetime < properties_start_datetime:
            message = "Property end_datetime can't refer to a date earlier than property "\
            "start_datetime"
            raise ValidationError(_(message))


def validate_item_properties_datetimes(
    properties_datetime, properties_start_datetime, properties_end_datetime, partial=False
):
    '''
    Validate datetime values in the properties Item attributes
    '''
    if not partial:
        # Do not validate dependencies in partial update, leave it to the validation to the model
        # instance.
        validate_item_properties_datetimes_dependencies(
            properties_datetime,
            properties_start_datetime,
            properties_end_datetime,
        )


def get_conformance_default_links():
    '''A helper function of the class Conformance Page

    The function makes it possible to define the default values as a callable
    Returns:
        a list of urls
    '''
    default_links = (
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core',
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30',
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson'
    )
    return default_links


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


class LandingPage(SingletonModel):
    # using "name" instead of "id", as "id" has a default meaning in django
    name = models.CharField(
        'id', unique=True, max_length=255, validators=[validate_name], default='ch'
    )
    title = models.CharField(max_length=255, default='data.geo.admin.ch')
    description = models.TextField(
        default='Data Catalog of the Swiss Federal Spatial Data Infrastructure'
    )

    def __str__(self):
        return "STAC Landing Page"

    class Meta:
        verbose_name = "STAC Landing Page"


class LandingPageLink(Link):
    landing_page = models.ForeignKey(
        LandingPage, related_name='links', related_query_name='link', on_delete=models.CASCADE
    )

    class Meta:
        unique_together = (('rel', 'landing_page'))


class ConformancePage(SingletonModel):
    conformsTo = ArrayField(  # pylint: disable=invalid-name
        models.URLField(
            blank=False,
            null=False
        ),
        default=get_conformance_default_links,
        help_text=_("Comma-separated list of URLs for the value conformsTo"))

    def __str__(self):
        return "Conformance Page"

    class Meta:
        verbose_name = "STAC Conformance Page"


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
    roles = ArrayField(
        models.CharField(max_length=9),
        help_text=_("Comma-separated list of roles. Possible values are {}".format(
            ', '.join(allowed_roles)
        )),
        blank=True,
        null=True,
    )
    url = models.URLField(blank=True, null=True)

    class Meta:
        unique_together = (('collection', 'name'),)

    def __str__(self):
        return self.name

    def clean(self):
        if self.roles is None:
            return
        for role in self.roles:
            if role not in self.allowed_roles:
                logger.error('Invalid role %s', role)
                raise ValidationError(_('Invalid role, must be in %s' % (self.allowed_roles)))


# For Collections and Items: No primary key will be defined, so that the auto-generated ones
# will be used by Django. For assets, a primary key is defined as "BigAutoField" due the
# expected large number of assets


class Collection(models.Model):
    # using "name" instead of "id", as "id" has a default meaning in django
    name = models.CharField('id', unique=True, max_length=255, validators=[validate_name])
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    description = models.TextField()
    extent_geometry = models.PolygonField(
        default=None,
        srid=4326,
        editable=False,
        blank=True,
        null=True,
        validators=[validate_geometry]
    )

    extent_start_datetime = models.DateTimeField(editable=False, null=True, blank=True)
    extent_end_datetime = models.DateTimeField(editable=False, null=True, blank=True)

    license = models.CharField(max_length=30)  # string

    # "summaries" values will be updated on every update of an asset inside the
    # collection
    summaries = models.JSONField(
        default=get_default_summaries_value, encoder=DjangoJSONEncoder, editable=False
    )
    title = models.CharField(blank=True, null=True, max_length=255)

    def __str__(self):
        return self.name

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
                self.name,
                item_name,
                action,
                error
            )
            raise GEOSException(
                f'Failed to update spatial extend in colletion {self.name} with item '
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


ITEM_KEEP_ORIGINAL_FIELDS = [
    'geometry',
    'properties_datetime',
    'properties_start_datetime',
    'properties_end_datetime',
]


class Item(models.Model):
    name = models.CharField(
        'id', unique=True, blank=False, max_length=255, validators=[validate_name]
    )
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE)
    geometry = models.PolygonField(
        null=False, blank=False, default=BBOX_CH, srid=4326, validators=[validate_geometry]
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    # after discussion with Chris and Tobias: for the moment only support
    # proterties: datetime and title (the rest is hence commented out)
    properties_datetime = models.DateTimeField(blank=True, null=True)
    properties_start_datetime = models.DateTimeField(blank=True, null=True)
    properties_end_datetime = models.DateTimeField(blank=True, null=True)
    # properties_eo_bands = model.TextFields(blank=True)  # ? [string]?
    # properties_eo_cloud_cover = models.FloatField(blank=True)
    # eo_gsd is defined on asset level and will be updated here on ever
    # update of an asset inside this item.
    # properties_instruments = models.TextField(blank=True)
    # properties_license = models.TextField(blank=True)
    # properties_platform = models.TextField(blank=True)
    # properties_providers = models.ManyToManyField(Provider)
    # Although it is discouraged by Django to set blank=True and null=True on a CharField, it is
    # here required because this field is optional and having an empty string value is not permitted
    # in the serializer and default to None. None value are then not displayed in the serializer.
    properties_title = models.CharField(blank=True, null=True, max_length=255)

    # properties_view_off_nadir = models.FloatField(blank=True)
    # properties_view_sun_azimuth = models.FloatField(blank=True)
    # properties_view_elevation = models.FloatField(blank=True)

    def __init__(self, *args, **kwargs):
        self._original_values = {}
        super().__init__(*args, **kwargs)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)

        # Save original values for some fields, when model is loaded from database,
        # in a separate attribute on the model, this simplify the collection extent update.
        # See https://docs.djangoproject.com/en/3.1/ref/models/instances/#customizing-model-loading
        instance._original_values = dict( # pylint: disable=protected-access
            filter(lambda item: item[0] in ITEM_KEEP_ORIGINAL_FIELDS, zip(field_names, values))
        )

        return instance

    def __str__(self):
        return self.name

    def clean(self):
        validate_item_properties_datetimes(
            self.properties_datetime, self.properties_start_datetime, self.properties_end_datetime
        )

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        # Make sure that the properties datetime are valid before updating the temporal extent
        # This is needed because save() is called during the Item.object.create() function without
        # calling clean() ! and our validation is done within clean() method.
        self.clean()
        if self.pk is None:
            action = "insert"
        else:
            action = "update"

        if self.properties_datetime is not None:
            if self._original_values.get('properties_datetime', None) is not None:
                # This is the case, when the value of properties.datetime has been
                # updated
                update_temporal_extent(
                    self,
                    self.collection,
                    action,
                    self._original_values['properties_datetime'],
                    self.properties_datetime,
                    self._original_values['properties_datetime'],
                    self.properties_datetime,
                    self.pk
                )
            else:
                # This is the case, when the item was defined by a start_ and
                # end_datetime before and has been changed to only have a single
                # datetime property. In that case, we hand over the old
                # start_ and end_datetime values to the update function, so
                # that a loop over all items will only be done, if really
                # necessary.

                update_temporal_extent(
                    self,
                    self.collection,
                    action,
                    self._original_values.get('properties_start_datetime', None),
                    self.properties_datetime,
                    self._original_values.get('properties_end_datetime', None),
                    self.properties_datetime,
                    self.pk
                )
        elif (
            self._original_values.get('properties_start_datetime', None) is not None and
            self._original_values.get('properties_end_datetime', None) is not None
        ):
            # This is the case, if an items values for start_ and/or end_datetime
            # were updated.
            update_temporal_extent(
                self,
                self.collection,
                action,
                self._original_values['properties_start_datetime'],
                self.properties_start_datetime,
                self._original_values['properties_end_datetime'],
                self.properties_end_datetime,
                self.pk
            )
        else:
            # This is the case, when an item was defined by a single datetime
            # before and has been changed to contain a start_ and an
            # end_datetime value now.
            update_temporal_extent(
                self,
                self.collection,
                action,
                self._original_values.get('properties_datetime', None),
                self.properties_start_datetime,
                self._original_values.get('properties_datetime', None),
                self.properties_end_datetime,
                self.pk
            )

        # adding a new item means updating the bbox of the collection
        if self.pk is None:
            self.collection.update_bbox_extent('insert', self.geometry, self.pk, self.name)
        # update the bbox of the collection only when the geometry of the item has changed
        elif self.geometry != self._original_values.get('geometry', None):
            self.collection.update_bbox_extent('update', self.geometry, self.pk, self.name)

        super().save(*args, **kwargs)

        # update the original_values just in case save() is called again without reloading from db
        self._original_values = {key: getattr(self, key) for key in ITEM_KEEP_ORIGINAL_FIELDS}

    def delete(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        if self.properties_datetime is not None:
            update_temporal_extent(
                self,
                self.collection,
                'remove',
                self._original_values.get('properties_datetime', None),
                self.properties_datetime,
                self._original_values.get('properties_datetime', None),
                self.properties_datetime,
                self.pk
            )
        else:
            update_temporal_extent(
                self,
                self.collection,
                'remove',
                self._original_values.get('properties_start_datetime', None),
                self.properties_start_datetime,
                self._original_values.get('properties_end_datetime', None),
                self.properties_end_datetime,
                self.pk
            )

        self.collection.update_bbox_extent('rm', self.geometry, self.pk, self.name)
        super().delete(*args, **kwargs)


class ItemLink(Link):
    item = models.ForeignKey(
        Item, related_name='links', related_query_name='link', on_delete=models.CASCADE
    )


ASSET_KEEP_ORIGINAL_FIELDS = ["eo_gsd", "geoadmin_variant", "proj_epsg"]


class Asset(models.Model):
    # using BigIntegerField as primary_key to deal with the expected large number of assets.
    id = models.BigAutoField(primary_key=True)
    item = models.ForeignKey(
        Item, related_name='assets', related_query_name='asset', on_delete=models.CASCADE
    )
    # using "name" instead of "id", as "id" has a default meaning in django
    name = models.CharField('id', unique=True, max_length=255, validators=[validate_name])
    checksum_multihash = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    eo_gsd = models.FloatField(null=True, blank=True)

    class Language(models.TextChoices):
        # pylint: disable=invalid-name
        GERMAN = 'de', _('German')
        ITALIAN = 'it', _('Italian')
        FRENCH = 'fr', _('French')
        ROMANSH = 'rm', _('Romansh')
        ENGLISH = 'en', _('English')
        NONE = '', _('')

    geoadmin_lang = models.CharField(
        max_length=2, choices=Language.choices, default=Language.NONE, null=True, blank=True
    )
    geoadmin_variant = models.CharField(
        max_length=15, null=True, blank=True, validators=[validate_geoadmin_variant]
    )
    proj_epsg = models.IntegerField(null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    media_type = models.CharField(max_length=200)
    href = models.URLField(max_length=255)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __init__(self, *args, **kwargs):
        self._original_values = {}
        super().__init__(*args, **kwargs)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)

        # Save original values for some fields, when model is loaded from database,
        # in a separate attribute on the model, this simplify the collection summaries update.
        # See https://docs.djangoproject.com/en/3.1/ref/models/instances/#customizing-model-loading
        instance._original_values = dict( # pylint: disable=protected-access
            filter(lambda item: item[0] in ASSET_KEEP_ORIGINAL_FIELDS, zip(field_names, values))
        )

        return instance

    def __str__(self):
        return self.name

    # alter save-function, so that the corresponding collection of the parent item of the asset
    # is saved, too.
    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        old_values = [
            self._original_values.get(field, None) for field in ASSET_KEEP_ORIGINAL_FIELDS
        ]
        update_summaries(self.item.collection, self, deleted=False, old_values=old_values)
        super().save(*args, **kwargs)

        # update the original_values just in case save() is called again without reloading from db
        self._original_values = {key: getattr(self, key) for key in ASSET_KEEP_ORIGINAL_FIELDS}

    def delete(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        update_summaries(self.item.collection, self, deleted=True, old_values=None)
        super().delete(*args, **kwargs)
