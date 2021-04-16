import hashlib
import logging
import os
import time
from uuid import uuid4

# import botocore.exceptions # Un-comment with BGDIINF_SB-1625
from multihash import encode as multihash_encode
from multihash import to_hex_string

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.gis.geos import Polygon
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.utils.translation import gettext_lazy as _

from solo.models import SingletonModel

from stac_api.collection_spatial_extent import CollectionSpatialExtentMixin
from stac_api.collection_summaries import UPDATE_SUMMARIES_FIELDS
from stac_api.collection_summaries import CollectionSummariesMixin
from stac_api.collection_temporal_extent import CollectionTemporalExtentMixin
from stac_api.managers import AssetUploadManager
from stac_api.managers import ItemManager
from stac_api.utils import get_asset_path
# from stac_api.utils import get_s3_resource # Un-comment with BGDIINF_SB-1625
from stac_api.validators import MEDIA_TYPES
from stac_api.validators import validate_asset_name
from stac_api.validators import validate_asset_name_with_media_type
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

SEARCH_TEXT_HELP_ITEM = '''
    <div class=SearchUsage>
        Search Usage:
        <ul>
            <li>
                <i>arg</i> will make a non exact search checking if <i>>arg</i>
                is part of the Item path
            </li>
            <li>
                Multiple <i>arg</i>  can be used, separated by spaces. This will search
                for all elements containing all arguments in their path
            </li>
            <li>
                <i>"collectionID/itemID"</i> will make an exact search for the specified item.
             </li>
        </ul>
        Examples :
        <ul>
            <li>
                Searching for <i>pixelkarte</i> will return all items which have
                pixelkarte as a part of either their collection ID or their item ID
            </li>
            <li>
                Searching for <i>pixelkarte 2016 4</i> will return all items
                which have pixelkarte, 2016 AND 4 as part of their collection ID or
                item ID
            </li>
            <li>
                Searching for <i>"ch.swisstopo.pixelkarte.example/item2016-4-example"</i>
                will yield only this item, if this item exists.
            </li>
        </ul>
    </div>'''

SEARCH_TEXT_HELP_COLLECTION = '''
    <div class=SearchUsage>
        Search Usage:
        <ul>
            <li>
                <i>arg</i> will make a non exact search checking if <i>arg</i> is part of
                the collection ID
            </li>
            <li>
                Multiple <i>arg</i> can be used, separated by spaces. This will search for all
                collections ID containing all arguments.
            </li>
            <li>
                <i>"collectionID"</i> will make an exact search for the specified collection.
            </li>
        </ul>
        Examples :
        <ul>
            <li>
                Searching for <i>pixelkarte</i> will return all collections which have
                pixelkarte as a part of their collection ID
            </li>
            <li>
                Searching for <i>pixelkarte 2016 4</i> will return all collection
                which have pixelkarte, 2016 AND 4 as part of their collection ID
            </li>
            <li>
                Searching for <i>ch.swisstopo.pixelkarte.example</i> will yield only this
                collection, if this collection exists. Please note that it would not return
                a collection named ch.swisstopo.pixelkarte.example.2.
            </li>
        </ul>
    </div>'''


def get_default_extent_value():
    return dict({"spatial": {"bbox": [[None]]}, "temporal": {"interval": [[None, None]]}})


def get_default_summaries_value():
    return dict({"eo:gsd": [], "geoadmin:variant": [], "proj:epsg": []})


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
        logger.debug('Saving CollectionProvider %s', self.name)
        super().save(*args, **kwargs)
        self.collection.save()  # save the collection to updated its ETag

    def clean(self):
        if self.roles is None:
            return
        for role in self.roles:
            if role not in self.allowed_roles:
                logger.error(
                    'Invalid provider role %s', role, extra={'collection', self.collection.name}
                )
                raise ValidationError(
                    _('Invalid role, must be in %(roles)s'),
                    params={'roles': self.allowed_roles},
                    code='roles'
                )


# For Collections and Items: No primary key will be defined, so that the auto-generated ones
# will be used by Django. For assets, a primary key is defined as "BigAutoField" due the
# expected large number of assets


class Collection(
    models.Model,
    CollectionSpatialExtentMixin,
    CollectionSummariesMixin,
    CollectionTemporalExtentMixin
):

    class Meta:
        indexes = [models.Index(fields=['name'], name='collection_name_idx')]

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
    etag = models.CharField(blank=False, null=False, editable=False, max_length=56)

    def __str__(self):
        return self.name

    def update_etag(self):
        '''Update the ETag with a new UUID
        '''
        logger.debug('Updating collection etag', extra={'collection': self.name})
        self.etag = compute_etag()

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        logger.debug('Saving collection', extra={'collection': self.name})
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
        logger.debug(
            'Saving collection link %s', self.rel, extra={'collection': self.collection.name}
        )
        super().save(*args, **kwargs)
        self.collection.save()  # save the collection to updated its ETag


ITEM_KEEP_ORIGINAL_FIELDS = [
    'geometry',
    'properties_datetime',
    'properties_start_datetime',
    'properties_end_datetime',
]


class Item(models.Model):

    class Meta:
        unique_together = (('collection', 'name'),)
        indexes = [
            models.Index(fields=['name'], name='item_name_idx'),
            # the following 3 indices are used e.g. in collection_temporal_extent
            models.Index(fields=['properties_datetime'], name='item_datetime_idx'),
            models.Index(fields=['properties_start_datetime'], name='item_start_datetime_idx'),
            models.Index(fields=['properties_end_datetime'], name='item_end_datetime_idx'),
            # created, updated, and title are "queriable" in the search endpoint
            # see: views.py:322 and 323
            models.Index(fields=['created'], name='item_created_idx'),
            models.Index(fields=['updated'], name='item_updated_idx'),
            models.Index(fields=['properties_title'], name='item_title_idx'),
            # combination of datetime and start_ and end_datetimes are used in
            # managers.py:110 and following
            models.Index(
                fields=[
                    'properties_datetime', 'properties_start_datetime', 'properties_end_datetime'
                ],
                name='item_dttme_start_end_dttm_idx'
            ),
        ]

    name = models.CharField('id', blank=False, max_length=255, validators=[validate_name])
    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, help_text=_(SEARCH_TEXT_HELP_COLLECTION)
    )
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
    etag = models.CharField(blank=False, null=False, editable=False, max_length=56)

    # Custom Manager that preselects the collection
    objects = ItemManager()

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
        # This is used in the admin page in the autocomplete_fields of the Asset page
        return f"{self.collection.name}/{self.name}"

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
        logger.debug('Saving item', extra={'collection': self.collection.name, 'item': self.name})
        collection_updated = False

        self.update_etag()

        trigger = get_save_trigger(self)

        collection_updated |= self.collection.update_temporal_extent(
            self, trigger, self._original_values
        )

        collection_updated |= self.collection.update_bbox_extent(
            trigger, self.geometry, self._original_values.get('geometry', None), self
        )

        if collection_updated:
            self.collection.save()

        super().save(*args, **kwargs)

        # update the original_values just in case save() is called again without reloading from db
        self._original_values = {key: getattr(self, key) for key in ITEM_KEEP_ORIGINAL_FIELDS}

    def delete(self, *args, **kwargs):  # pylint: disable=signature-differs
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        logger.debug('Deleting item', extra={'collection': self.collection.name, 'item': self.name})
        collection_updated = False

        collection_updated |= self.collection.update_temporal_extent(
            self, 'delete', self._original_values
        )

        collection_updated |= self.collection.update_bbox_extent(
            'delete', self.geometry, None, self
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
        logger.debug(
            'Saving item link %s',
            self.rel,
            extra={
                'collection': self.item.collection.name, 'item': self.item.name
            }
        )
        super().save(*args, **kwargs)
        self.item.save()  # We save the item to update its ETag


ASSET_KEEP_ORIGINAL_FIELDS = ["name", "file"] + UPDATE_SUMMARIES_FIELDS


def upload_asset_to_path_hook(instance, filename=None):
    '''This returns the asset upload path on S3 and compute the asset file multihash

    Args:
        instance: Asset
            Asset instance
        filename: string
            file name of the uploaded asset

    Returns:
        Asset file path to use on S3
    '''
    logger.debug('Start computing asset file %s multihash', filename)
    start = time.time()
    ctx = hashlib.sha256()
    for chunk in instance.file.chunks(settings.UPLOAD_FILE_CHUNK_SIZE):
        ctx.update(chunk)
    mhash = to_hex_string(multihash_encode(ctx.digest(), 'sha2-256'))
    # set the hash to the storage to use it for upload signing, this temporary attribute is
    # then used by storages.S3Storage to set the MetaData.sha256
    setattr(instance.file.storage, '_tmp_sha256', ctx.hexdigest())
    logger.debug(
        'Set uploaded file %s multihash %s to checksum:multihash; computation done in %ss',
        filename,
        mhash,
        time.time() - start
    )
    instance.checksum_multihash = mhash
    return get_asset_path(instance.item, instance.name)


class Asset(models.Model):

    class Meta:
        unique_together = (('item', 'name'),)

    # using BigIntegerField as primary_key to deal with the expected large number of assets.
    id = models.BigAutoField(primary_key=True)
    item = models.ForeignKey(
        Item,
        related_name='assets',
        related_query_name='asset',
        on_delete=models.CASCADE,
        help_text=_(SEARCH_TEXT_HELP_ITEM)
    )
    # using "name" instead of "id", as "id" has a default meaning in django
    name = models.CharField('id', max_length=255, validators=[validate_asset_name])
    file = models.FileField(upload_to=upload_asset_to_path_hook, max_length=255)

    @property
    def filename(self):
        return os.path.basename(self.file.name)

    checksum_multihash = models.CharField(
        editable=False, max_length=255, blank=True, null=True, default=None
    )
    # here we need to set blank=True otherwise the field is as required in the admin interface
    description = models.TextField(blank=True, null=True, default=None)
    eo_gsd = models.FloatField(null=True, blank=True)

    class Language(models.TextChoices):
        # pylint: disable=invalid-name
        GERMAN = 'de', _('German')
        ITALIAN = 'it', _('Italian')
        FRENCH = 'fr', _('French')
        ROMANSH = 'rm', _('Romansh')
        ENGLISH = 'en', _('English')
        __empty__ = _('')

    # here we need to set blank=True otherwise the field is as required in the admin interface
    geoadmin_lang = models.CharField(
        max_length=2, choices=Language.choices, default=None, null=True, blank=True
    )
    # here we need to set blank=True otherwise the field is as required in the admin interface
    geoadmin_variant = models.CharField(
        max_length=25, null=True, blank=True, validators=[validate_geoadmin_variant]
    )
    proj_epsg = models.IntegerField(null=True, blank=True)
    # here we need to set blank=True otherwise the field is as required in the admin interface
    title = models.CharField(max_length=255, null=True, blank=True)
    media_choices = [(x[0], f'{x[1]} ({x[0]})') for x in MEDIA_TYPES]
    media_type = models.CharField(choices=media_choices, max_length=200, blank=False, null=False)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # hidden ETag field
    etag = models.CharField(blank=False, null=False, editable=False, max_length=56)

    def __init__(self, *args, **kwargs):
        self._original_values = {}
        super().__init__(*args, **kwargs)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)

        # Save original values for some fields, when model is loaded from database,
        # in a separate attribute on the model, this simplify the collection summaries update.
        # See https://docs.djangoproject.com/en/3.1/ref/models/instances/#customizing-model-loading
        instance.keep_originals(field_names, values)  # pylint: disable=no-member

        return instance

    def __str__(self):
        return self.name

    def keep_originals(self, field_names, values):
        self._original_values = dict( # pylint: disable=protected-access
            filter(lambda item: item[0] in ASSET_KEEP_ORIGINAL_FIELDS, zip(field_names, values))
        )

        # file.name / path has to be treated separately since it's not a simple
        # field
        self._original_values['path'] = self.file.name

    def update_etag(self):
        '''Update the ETag with a new UUID
        '''
        self.etag = compute_etag()

    # alter save-function, so that the corresponding collection of the parent item of the asset
    # is saved, too.
    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        logger.debug(
            'Saving asset',
            extra={
                'collection': self.item.collection.name, 'item': self.item.name, 'asset': self.name
            }
        )
        self.update_etag()

        trigger = get_save_trigger(self)

        old_values = [self._original_values.get(field, None) for field in UPDATE_SUMMARIES_FIELDS]

        if self.item.collection.update_summaries(self, trigger, old_values=old_values):
            self.item.collection.save()

        self.item.save()  # We save the item to update its ETag

        super().save(*args, **kwargs)

        # update the original_values just in case save() is called again without reloading from db
        fields = [field.name for field in self._meta.get_fields()]
        self.keep_originals(fields, [getattr(self, field) for field in fields])

    def delete(self, *args, **kwargs):  # pylint: disable=signature-differs
        logger.debug(
            'Deleting asset',
            extra={
                'collection': self.item.collection.name, 'item': self.item.name, 'asset': self.name
            }
        )
        # It is important to use `*args, **kwargs` in signature because django might add dynamically
        # parameters
        if self.item.collection.update_summaries(self, 'delete', old_values=None):
            self.item.collection.save()
        self.item.save()  # We save the item to update its ETag
        try:
            super().delete(*args, **kwargs)
        except ProtectedError as error:
            logger.error(
                'Cannot delete asset %s: %s',
                self.name,
                error,
                extra={
                    'collection': self.item.collection.name,
                    'item': self.item.name,
                    'asset': self.name
                }
            )
            raise ValidationError(error.args[0]) from None

    def clean(self):
        validate_asset_name_with_media_type(self.name, self.media_type)


class AssetUpload(models.Model):

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['asset', 'upload_id'], name='unique_together'),
            # Make sure that there is only one asset upload in progress per asset
            models.UniqueConstraint(
                fields=['asset', 'status'],
                condition=Q(status='in-progress'),
                name='unique_in_progress'
            )
        ]

    class Status(models.TextChoices):
        # pylint: disable=invalid-name
        IN_PROGRESS = 'in-progress'
        COMPLETED = 'completed'
        ABORTED = 'aborted'
        __empty__ = ''

    # using BigIntegerField as primary_key to deal with the expected large number of assets.
    id = models.BigAutoField(primary_key=True)
    asset = models.ForeignKey(Asset, related_name='+', on_delete=models.CASCADE)
    upload_id = models.CharField(max_length=255, blank=False, null=False)
    status = models.CharField(
        choices=Status.choices, max_length=32, default=Status.IN_PROGRESS, blank=False, null=False
    )
    number_parts = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)], null=False, blank=False
    )  # S3 doesn't support more that 10'000 parts
    urls = models.JSONField(default=list, encoder=DjangoJSONEncoder, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    ended = models.DateTimeField(blank=True, null=True, default=None)
    checksum_multihash = models.CharField(max_length=255, blank=False, null=False)

    # hidden ETag field
    etag = models.CharField(blank=False, null=False, max_length=56, default=compute_etag)

    # Custom Manager that preselects the collection
    objects = AssetUploadManager()

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        self.update_etag()
        super().save(*args, **kwargs)

    def update_etag(self):
        '''Update the ETag with a new UUID
        '''
        self.etag = compute_etag()

    def update_asset_checksum_multihash(self):
        '''Updating the asset's checksum:multihash from the upload

        When the upload is completed, the new checksum:multihash from the upload
        is set to its asset parent.
        '''
        logger.debug(
            'Updating asset %s checksum:multihash from %s to %s due to upload complete',
            self.asset.name,
            self.asset.checksum_multihash,
            self.checksum_multihash,
            extra={
                'upload_id': self.upload_id,
                'asset': self.asset.name,
                'item': self.asset.item.name,
                'collection': self.asset.item.collection.name
            }
        )
        self.asset.checksum_multihash = self.checksum_multihash
        self.asset.save()
