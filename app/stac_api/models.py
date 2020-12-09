import logging
import os
import re
from uuid import uuid4

from django.contrib.gis.db import models
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Polygon
from django.contrib.gis.geos.error import GEOSException
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.translation import gettext_lazy as _

from solo.models import SingletonModel

from stac_api.collection_summaries import UPDATE_SUMMARIES_FIELDS
from stac_api.collection_summaries import update_summaries_on_asset_delete
from stac_api.collection_summaries import update_summaries_on_asset_insert
from stac_api.collection_summaries import update_summaries_on_asset_update
from stac_api.temporal_extent import update_temporal_extent
from stac_api.validators import MEDIA_TYPES
from stac_api.validators import validate_geoadmin_variant
from stac_api.validators import validate_geometry
from stac_api.validators import validate_item_properties_datetimes
from stac_api.validators import validate_link_rel
from stac_api.validators import validate_name

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


def compute_etag():
    '''Compute a unique ETag'''
    return str(uuid4())


def get_save_trigger(instance):
    '''Get the model instance save() trigger event

    Returns:
        'insert' or 'update'
    '''
    trigger = 'update'
    if instance.pk is None:
        trigger = 'insert'
    return trigger


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

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        super().save(*args, **kwargs)
        self.collection.save()  # save the collection to updated its ETag

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

    # hidden ETag field
    etag = models.CharField(
        blank=False, null=False, editable=False, max_length=56, default=str(uuid4())
    )

    def __str__(self):
        return self.name

    def update_etag(self):
        '''Update the ETag with a new UUID
        '''
        self.etag = compute_etag()

    def update_bbox_extent(self, trigger, geometry, original_geometry, item_id, item_name):
        '''Updates the collection's spatial extent if needed when an item is updated.

        This function generates a new extent regarding all the items with the same
        collection foreign key. If there is no spatial bbox yet, the one of the geometry of the
        item is being used.

        Args:
            trigger: str
                Item trigger event, one of 'insert', 'update' or 'delete'
            geometry: GeometryField
                the geometry of the item
            original_geometry:
                the original geometry during an updated or None
            item_id: int
                the id (pk) of the item being treated
            item_name: str
                the item name being treated

        Returns:
            bool: True if the collection temporal extent has been updated, false otherwise
        '''
        updated = False
        try:
            # insert (as item_id is None)
            if trigger == 'insert':
                logger.debug('Updating collections extent_geometry' ' as a item has been inserted')
                # the first item of this collection
                if self.extent_geometry is None:
                    self.extent_geometry = Polygon.from_bbox(GEOSGeometry(geometry).extent)
                # there is already a geometry in the collection a union of the geometries
                else:
                    self.extent_geometry = Polygon.from_bbox(
                        GEOSGeometry(self.extent_geometry).union(GEOSGeometry(geometry)).extent
                    )
                updated |= True

            # update
            if trigger == 'update' and geometry != original_geometry:
                logger.debug(
                    'Updating collections extent_geometry'
                    ' as a item geometry has been updated'
                )
                # is the new bbox larger than (and covering) the existing
                if Polygon.from_bbox(GEOSGeometry(geometry).extent).covers(self.extent_geometry):
                    self.extent_geometry = Polygon.from_bbox(GEOSGeometry(geometry).extent)
                # we need to iterate trough the items
                else:
                    logger.warning(
                        'Looping over all items of collection %s,'
                        'to update extent_geometry, this may take a while',
                        self.pk
                    )
                    qs = Item.objects.filter(collection_id=self.pk).exclude(id=item_id)
                    union_geometry = GEOSGeometry(geometry)
                    for item in qs:
                        union_geometry = union_geometry.union(item.geometry)
                    self.extent_geometry = Polygon.from_bbox(union_geometry.extent)
                updated |= True

            # delete, we need to iterate trough the items
            if trigger == 'delete':
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
                updated |= True
        except GEOSException as error:
            logger.error(
                'Failed to update spatial extend in collection %s with item %s trigger=%s: %s',
                self.name,
                item_name,
                trigger,
                error
            )
            raise GEOSException(
                f'Failed to update spatial extend in colletion {self.name} with item '
                f'{item_name}: {error}'
            )
        return updated

    def update_temporal_extent(self, item, trigger, original_item_values):
        '''Updates the collection's temporal extent if needed when items are inserted, updated or
        deleted.

        For all the given parameters this function checks, if the corresponding parameters of the
        collection need to be updated. If so, they will be updated.

        Args:
            item:
                Item thats being inserted/updated or deleted
            trigger:
                Item trigger event, one of 'insert', 'update' or 'delete'
            original_item_values: (optional)
                Dictionary with the original values of item's ['properties_datetime',
                'properties_start_datetime', 'properties_end_datetime'].

        Returns:
            bool: True if the collection summaries has been updated, false otherwise
        '''
        updated = False

        # Get the start end datetimes independently if we have a range or not, when there is no
        # range then we use the same start and end datetime
        start_datetime = item.properties_start_datetime
        end_datetime = item.properties_end_datetime
        if start_datetime is None or end_datetime is None:
            start_datetime = item.properties_datetime
            end_datetime = item.properties_datetime

        # Get the original start end datetimes independently if we have a range or not, when there
        # is no range then we use the same start and end datetime
        old_start_datetime = original_item_values.get('properties_start_datetime', None)
        old_end_datetime = original_item_values.get('properties_end_datetime', None)
        if old_start_datetime is None or old_end_datetime is None:
            old_start_datetime = original_item_values.get('properties_datetime', None)
            old_end_datetime = original_item_values.get('properties_datetime', None)

        if trigger == 'insert':
            updated |= update_temporal_extent(
                self, item, trigger, None, start_datetime, None, end_datetime
            )
        elif trigger in ['update', 'delete']:
            updated |= update_temporal_extent(
                self,
                item,
                trigger,
                old_start_datetime,
                start_datetime,
                old_end_datetime,
                end_datetime
            )
        else:
            raise ValueError(f'Invalid trigger parameter; {trigger}')

        return updated

    def update_summaries(self, asset, trigger, old_values=None):
        '''Updates the collection's summaries if needed when assets are updated or deleted.

        For all the given parameters this function checks, if the corresponding parameters of the
        collection need to be updated. If so, they will be updated.

        Args:
            asset:
                Asset thats being inserted/updated or deleted
            trigger:
                Asset trigger event, one of 'insert', 'update' or 'delete'
            old_values: (optional)
                List with the original values of asset's [eo_gsd, geoadmin_variant, proj_epsg].

        Returns:
            bool: True if the collection summaries has been updated, false otherwise
        '''

        if trigger == 'delete':
            return update_summaries_on_asset_delete(self, asset)
        if trigger == 'update':
            return update_summaries_on_asset_update(self, asset, old_values)
        if trigger == 'insert':
            return update_summaries_on_asset_insert(self, asset)
        raise ValueError(f'Invalid trigger parameter: {trigger}')

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

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        self.update_etag()
        super().save(*args, **kwargs)


class CollectionLink(Link):
    collection = models.ForeignKey(
        Collection, related_name='links', related_query_name='link', on_delete=models.CASCADE
    )

    class Meta:
        unique_together = (('rel', 'collection'),)

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        super().save(*args, **kwargs)
        self.collection.save()  # save the collection to updated its ETag


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

    # hidden ETag field
    etag = models.CharField(
        blank=False, null=False, editable=False, max_length=56, default=str(uuid4())
    )

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

    def update_etag(self):
        '''Update the ETag with a new UUID
        '''
        self.etag = compute_etag()

    def clean(self):
        validate_item_properties_datetimes(
            self.properties_datetime, self.properties_start_datetime, self.properties_end_datetime
        )

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        collection_updated = False

        # Make sure that the properties datetime are valid before updating the temporal extent
        # This is needed because save() is called during the Item.object.create() function without
        # calling clean() ! and our validation is done within clean() method.
        self.clean()

        self.update_etag()

        trigger = get_save_trigger(self)

        collection_updated |= self.collection.update_temporal_extent(
            self, trigger, self._original_values
        )

        collection_updated |= self.collection.update_bbox_extent(
            trigger, self.geometry, self._original_values.get('geometry', None), self.pk, self.name
        )

        if collection_updated:
            self.collection.save()

        super().save(*args, **kwargs)

        # update the original_values just in case save() is called again without reloading from db
        self._original_values = {key: getattr(self, key) for key in ITEM_KEEP_ORIGINAL_FIELDS}

    def delete(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        collection_updated = False

        collection_updated |= self.collection.update_temporal_extent(
            self, 'delete', self._original_values
        )

        collection_updated |= self.collection.update_bbox_extent(
            'delete', self.geometry, None, self.pk, self.name
        )

        if collection_updated:
            self.collection.save()

        super().delete(*args, **kwargs)


class ItemLink(Link):
    item = models.ForeignKey(
        Item, related_name='links', related_query_name='link', on_delete=models.CASCADE
    )

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        super().save(*args, **kwargs)
        self.item.save()  # We save the item to update its ETag


ASSET_KEEP_ORIGINAL_FIELDS = ["name"] + UPDATE_SUMMARIES_FIELDS


def get_upload_to_asset_path(instance, filename):
    return '/'.join([instance.item.collection.name, instance.item.name, instance.name])


class Asset(models.Model):
    # using BigIntegerField as primary_key to deal with the expected large number of assets.
    id = models.BigAutoField(primary_key=True)
    item = models.ForeignKey(
        Item, related_name='assets', related_query_name='asset', on_delete=models.CASCADE
    )
    # using "name" instead of "id", as "id" has a default meaning in django
    name = models.CharField('id', unique=True, max_length=255, validators=[validate_name])
    file = models.FileField(upload_to=get_upload_to_asset_path, null=True, blank=True)

    @property
    def filename(self):
        return os.path.basename(self.file.name)

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
    media_choices = [(x[0], f'{x[1]} ({x[0]})') for x in MEDIA_TYPES]
    media_type = models.CharField(choices=media_choices, max_length=200, blank=False, null=False)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # hidden ETag field
    etag = models.CharField(
        blank=False, null=False, editable=False, max_length=56, default=str(uuid4())
    )

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

    def update_etag(self):
        '''Update the ETag with a new UUID
        '''
        self.etag = compute_etag()

    def clean(self):
        if (
            self._original_values.get("name") is not None and
            self.name != self._original_values.get("name")
        ):
            message = "Renaming assets is currently not supported"
            logger.error(message)
            raise ValidationError({"name": _(message)})

    # alter save-function, so that the corresponding collection of the parent item of the asset
    # is saved, too.
    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        self.update_etag()

        trigger = get_save_trigger(self)

        old_values = [self._original_values.get(field, None) for field in UPDATE_SUMMARIES_FIELDS]
        if self.item.collection.update_summaries(self, trigger, old_values=old_values):
            self.item.collection.save()

        self.item.save()  # We save the item to update its ETag

        super().save(*args, **kwargs)

        # update the original_values just in case save() is called again without reloading from db
        self._original_values = {key: getattr(self, key) for key in UPDATE_SUMMARIES_FIELDS}

    def delete(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        if self.item.collection.update_summaries(self, 'delete', old_values=None):
            self.item.collection.save()
        self.item.save()  # We save the item to update its ETag
        super().delete(*args, **kwargs)
