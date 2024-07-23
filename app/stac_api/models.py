import hashlib
import logging
import os
import time
from uuid import uuid4

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

from stac_api.managers import AssetUploadManager
from stac_api.managers import ItemManager
from stac_api.pgtriggers import generate_child_triggers
from stac_api.pgtriggers import generate_collection_asset_triggers
from stac_api.pgtriggers import generates_asset_triggers
from stac_api.pgtriggers import generates_asset_upload_triggers
from stac_api.pgtriggers import generates_collection_triggers
from stac_api.pgtriggers import generates_item_triggers
from stac_api.utils import get_asset_path
from stac_api.utils import get_collection_asset_path
from stac_api.utils import select_s3_bucket
from stac_api.validators import MEDIA_TYPES
from stac_api.validators import validate_asset_name
from stac_api.validators import validate_asset_name_with_media_type
from stac_api.validators import validate_eo_gsd
from stac_api.validators import validate_geoadmin_variant
from stac_api.validators import validate_geometry
from stac_api.validators import validate_item_properties_datetimes
from stac_api.validators import validate_link_rel
from stac_api.validators import validate_media_type
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


def get_conformance_default_links():
    '''A helper function of the class Conformance Page

    The function makes it possible to define the default values as a callable
    Returns:
        a list of urls
    '''
    default_links = (
        'https://api.stacspec.org/v1.0.0/core',
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core',
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30',
        'http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson'
    )
    return default_links


def get_default_summaries_value():
    return {}


def compute_etag():
    '''Compute a unique ETag'''
    return str(uuid4())


class Link(models.Model):
    href = models.URLField(max_length=2048)
    rel = models.CharField(max_length=30, validators=[validate_link_rel])
    # added link_ to the fieldname, as "type" is reserved
    link_type = models.CharField(blank=True, null=True, max_length=150)
    title = models.CharField(blank=True, null=True, max_length=255)

    class Meta:
        abstract = True

    def __str__(self):
        return f'{self.rel}: {self.href}'


class LandingPage(models.Model):
    # using "name" instead of "id", as "id" has a default meaning in django
    name = models.CharField(
        'id', unique=False, max_length=255, validators=[validate_name], default='ch'
    )
    title = models.CharField(max_length=255, default='data.geo.admin.ch')
    description = models.TextField(
        default='Data Catalog of the Swiss Federal Spatial Data Infrastructure'
    )
    version = models.CharField(max_length=255, default='v1')

    conformsTo = ArrayField(  # pylint: disable=invalid-name
        models.URLField(
            blank=False,
            null=False
        ),
        default=get_conformance_default_links,
        help_text=_("Comma-separated list of URLs for the value conformsTo"))

    def __str__(self):
        return f'STAC Landing Page {self.version}'

    class Meta:
        verbose_name = "STAC Landing Page"


class LandingPageLink(Link):
    landing_page = models.ForeignKey(
        LandingPage, related_name='links', related_query_name='link', on_delete=models.CASCADE
    )

    class Meta:
        unique_together = (('rel', 'landing_page'))
        ordering = ['pk']


class Provider(models.Model):
    collection = models.ForeignKey(
        'stac_api.Collection',
        on_delete=models.CASCADE,
        related_name='providers',
        related_query_name='provider'
    )
    name = models.CharField(blank=False, max_length=200)
    description = models.TextField(blank=True, null=True, default=None)
    # possible roles are licensor, producer, processor or host
    allowed_roles = ['licensor', 'producer', 'processor', 'host']
    roles = ArrayField(
        models.CharField(max_length=9),
        help_text=_(
            f"Comma-separated list of roles. Possible values are {', '.join(allowed_roles)}"
        ),
        blank=True,
        null=True,
    )
    url = models.URLField(blank=True, null=True, max_length=2048)

    class Meta:
        unique_together = (('collection', 'name'),)
        ordering = ['pk']
        triggers = generate_child_triggers('collection', 'Provider')

    def __str__(self):
        return self.name

    def clean(self):
        if self.roles is None:
            return
        for role in self.roles:
            if role not in self.allowed_roles:
                logger.error(
                    'Invalid provider role %s', role, extra={'collection': self.collection.name}
                )
                raise ValidationError(
                    _('Invalid role, must be in %(roles)s'),
                    params={'roles': self.allowed_roles},
                    code='roles'
                )


# For Collections and Items: No primary key will be defined, so that the auto-generated ones
# will be used by Django. For assets, a primary key is defined as "BigAutoField" due the
# expected large number of assets
class Collection(models.Model):

    class Meta:
        indexes = [
            models.Index(fields=['name'], name='collection_name_idx'),
            models.Index(fields=['published'], name='collection_published_idx')
        ]
        triggers = generates_collection_triggers()

    published = models.BooleanField(
        default=True,
        help_text="When not published the collection doesn't appear on the "
        "api/stac/v0.9/collections endpoint and its items are not listed in /search endpoint."
        "<p><i>NOTE: unpublished collections/items can still be accessed by their path.</ip></p>"
    )
    # using "name" instead of "id", as "id" has a default meaning in django
    name = models.CharField('id', unique=True, max_length=255, validators=[validate_name])
    created = models.DateTimeField(auto_now_add=True)
    # NOTE: the updated field is automatically updated by stac_api.pgtriggers, we use auto_now_add
    # only for the initial value.
    updated = models.DateTimeField(auto_now_add=True)
    description = models.TextField()
    extent_geometry = models.GeometryField(
        default=None, srid=4326, editable=False, blank=True, null=True
    )
    extent_start_datetime = models.DateTimeField(editable=False, null=True, blank=True)
    extent_end_datetime = models.DateTimeField(editable=False, null=True, blank=True)

    license = models.CharField(max_length=30)  # string

    # DEPRECATED: summaries JSON field is not used anymore and not up to date, it will be removed
    # in future. It has been replaced by summaries_proj_epsg, summaries_eo_gsd and
    # summaries_geoadmin_variant
    summaries = models.JSONField(default=dict, encoder=DjangoJSONEncoder, editable=False)

    # NOTE: the following summaries_* fields are automatically update by the stac_api.pgtriggers
    summaries_proj_epsg = ArrayField(
        models.IntegerField(), default=list, blank=True, editable=False
    )
    summaries_eo_gsd = ArrayField(models.FloatField(), default=list, blank=True, editable=False)
    summaries_geoadmin_variant = ArrayField(
        models.CharField(max_length=25), default=list, blank=True, editable=False
    )
    summaries_geoadmin_lang = ArrayField(
        models.CharField(max_length=2), default=list, blank=True, editable=False
    )

    title = models.CharField(blank=True, null=True, max_length=255)

    # NOTE: hidden ETag field, this field is automatically updated by stac_api.pgtriggers
    etag = models.CharField(
        blank=False, null=False, editable=False, max_length=56, default=compute_etag
    )

    update_interval = models.IntegerField(
        default=-1,
        null=False,
        blank=False,
        validators=[MinValueValidator(-1)],
        help_text="Minimal update interval in seconds "
        "in which the underlying assets data are updated."
    )

    allow_external_assets = models.BooleanField(
        default=False,
        help_text=_('Whether this collection can have assets that are hosted externally')
    )

    external_asset_whitelist = ArrayField(
        models.CharField(max_length=255), blank=True, default=list,
        help_text=_('Provide a comma separated list of '
                    'protocol://domain values for the external asset url validation')
    )

    def __str__(self):
        return self.name


class CollectionLink(Link):
    collection = models.ForeignKey(
        Collection, related_name='links', related_query_name='link', on_delete=models.CASCADE
    )

    class Meta:
        unique_together = (('rel', 'collection'),)
        ordering = ['pk']
        triggers = generate_child_triggers('collection', 'CollectionLink')


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
            # created, updated, and title are "queryable" in the search endpoint
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
            models.Index(fields=['update_interval'], name='item_update_interval_idx'),
        ]
        triggers = generates_item_triggers()

    name = models.CharField('id', blank=False, max_length=255, validators=[validate_name])
    collection = models.ForeignKey(
        Collection, on_delete=models.PROTECT, help_text=_(SEARCH_TEXT_HELP_COLLECTION)
    )
    geometry = models.GeometryField(
        null=False, blank=False, default=BBOX_CH, srid=4326, validators=[validate_geometry]
    )
    created = models.DateTimeField(auto_now_add=True)
    # NOTE: the updated field is automatically updated by stac_api.pgtriggers, we use auto_now_add
    # only for the initial value.
    updated = models.DateTimeField(auto_now_add=True)
    # after discussion with Chris and Tobias: for the moment only support
    # proterties: datetime and title (the rest is hence commented out)
    properties_datetime = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Enter date in <i>yyyy-mm-dd</i> format, and time in UTC <i>hh:mm:ss</i> format"
    )
    properties_start_datetime = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Enter date in <i>yyyy-mm-dd</i> format, and time in UTC <i>hh:mm:ss</i> format"
    )
    properties_end_datetime = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Enter date in <i>yyyy-mm-dd</i> format, and time in UTC <i>hh:mm:ss</i> format"
    )
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

    # NOTE: hidden ETag field, this field is automatically updated by stac_api.pgtriggers
    etag = models.CharField(
        blank=False, null=False, editable=False, max_length=56, default=compute_etag
    )

    update_interval = models.IntegerField(
        default=-1,
        null=False,
        blank=False,
        validators=[MinValueValidator(-1)],
        help_text="Minimal update interval in seconds "
        "in which the underlying assets data are updated."
    )

    # Custom Manager that preselects the collection
    objects = ItemManager()

    def __str__(self):
        # This is used in the admin page in the autocomplete_fields of the Asset page
        return f"{self.collection.name}/{self.name}"

    def clean(self):
        validate_item_properties_datetimes(
            self.properties_datetime, self.properties_start_datetime, self.properties_end_datetime
        )


class ItemLink(Link):
    item = models.ForeignKey(
        Item, related_name='links', related_query_name='link', on_delete=models.CASCADE
    )

    class Meta:
        unique_together = (('rel', 'item'),)
        ordering = ['pk']
        triggers = generate_child_triggers('item', 'ItemLink')


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
    item_name = 'no item on collection asset'
    if hasattr(instance, 'item'):
        item_name = instance.item.name
    logger.debug(
        'Start computing asset file %s multihash (file size: %.1f MB)',
        filename,
        instance.file.size / 1024**2,
        extra={
            "collection": instance.get_collection().name, "item": item_name, "asset": instance.name
        }
    )
    start = time.time()
    ctx = hashlib.sha256()
    for chunk in instance.file.chunks(settings.UPLOAD_FILE_CHUNK_SIZE):
        ctx.update(chunk)
    mhash = to_hex_string(multihash_encode(ctx.digest(), 'sha2-256'))
    # set the hash to the storage to use it for upload signing, this temporary attribute is
    # then used by storages.S3Storage to set the MetaData.sha256
    instance.file.storage.object_sha256 = ctx.hexdigest()
    # Same here for the update_interval that is used by the storages.S3Storage to set the asset's
    # update_interval
    instance.file.storage.update_interval = instance.update_interval
    logger.debug(
        'Set uploaded file %s multihash %s to file:checksum; computation done in %.3fs',
        filename,
        mhash,
        time.time() - start,
        extra={
            "collection": instance.get_collection().name, "item": item_name, "asset": instance.name
        }
    )
    instance.checksum_multihash = mhash
    return instance.get_asset_path()


class DynamicStorageFileField(models.FileField):

    def pre_save(self, model_instance: "AssetBase", add):
        """Determine the storage to use for this file

        The storage is determined by the collection's name. See
        settings.MANAGED_BUCKET_COLLECTION_PATTERNS
        """
        collection = model_instance.get_collection()

        bucket = select_s3_bucket(collection.name).name

        # We need to explicitly instantiate the storage backend here
        # Since the backends are configured as strings in the settings, we take these strings
        # and import them by those string
        # Example is stac_api.storages.LegacyS3Storage
        parts = settings.STORAGES[bucket]['BACKEND'].split(".")

        # join the first two parts of the module name together -> stac_api.storages
        storage_module_name = ".".join(parts[:-1])

        # the name of the storage class is the last part -> LegacyS3Storage
        storage_cls_name = parts[-1:]

        # import the module
        storage_module = __import__(storage_module_name, fromlist=[parts[-2:-1]])

        # get the class from the module
        storage_cls = getattr(storage_module, storage_cls_name[0])

        # .. and instantiate!
        self.storage = storage_cls()

        # we need to specify the storage for the actual
        # file as well
        model_instance.file.storage = self.storage

        self.storage.asset_content_type = model_instance.media_type

        return super().pre_save(model_instance, add)


class AssetBase(models.Model):

    class Meta:
        abstract = True

    # using BigIntegerField as primary_key to deal with the expected large number of assets.
    id = models.BigAutoField(primary_key=True)

    # using "name" instead of "id", as "id" has a default meaning in django
    name = models.CharField('id', max_length=255, validators=[validate_asset_name])

    # Disable weird pylint errors, where it doesn't take the inherited constructor
    # into account when linting, somehow
    # pylint: disable=unexpected-keyword-arg
    # pylint: disable=no-value-for-parameter
    file = DynamicStorageFileField(upload_to=upload_asset_to_path_hook, max_length=255)
    roles = ArrayField(
        models.CharField(max_length=255), editable=True, blank=True, null=True, default=None,
        help_text=_("Comma-separated list of roles to describe the purpose of the asset"))

    @property
    def filename(self):
        return os.path.basename(self.file.name)

    # From v1 on the json representation of this field changed from "checksum:multihash" to
    # "file:checksum". The two names may be used interchangeably for a now.
    checksum_multihash = models.CharField(
        editable=False, max_length=255, blank=True, null=True, default=None
    )
    # here we need to set blank=True otherwise the field is as required in the admin interface
    description = models.TextField(blank=True, null=True, default=None)

    proj_epsg = models.IntegerField(null=True, blank=True)
    # here we need to set blank=True otherwise the field is as required in the admin interface
    title = models.CharField(max_length=255, null=True, blank=True)
    media_choices = [
        (x.media_type_str, f'{x.description} ({x.media_type_str})') for x in MEDIA_TYPES
    ]
    media_type = models.CharField(
        choices=media_choices,
        max_length=200,
        blank=False,
        null=False,
        help_text=
        "This media type will be used as <em>Content-Type</em> header for the asset's object upon "
        "upload.</br></br>"
        "<b>WARNING: when updating the Media Type, the asset's object Content-Type header is not "
        "automatically updated, it needs to be uploaded again.</b>"
    )

    created = models.DateTimeField(auto_now_add=True)
    # NOTE: the updated field is automatically updated by stac_api.pgtriggers, we use auto_now_add
    # only for the initial value.
    updated = models.DateTimeField(auto_now_add=True)

    # NOTE: hidden ETag field, this field is automatically updated by stac_api.pgtriggers
    etag = models.CharField(
        blank=False, null=False, editable=False, max_length=56, default=compute_etag
    )

    update_interval = models.IntegerField(
        default=-1,
        null=False,
        blank=False,
        validators=[MinValueValidator(-1)],
        help_text="Interval in seconds in which the asset data is updated."
        "-1 means that the data is not on a regular basis updated."
    )

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):  # pylint: disable=signature-differs
        try:
            super().delete(*args, **kwargs)
        except ProtectedError as error:
            logger.error('Cannot delete asset %s: %s', self.name, error)
            raise ValidationError(error.args[0]) from None

    def clean(self):
        # Although the media type is already validated, it still needs to be validated a second
        # time as the clean method is run even if the field validation failed and there is no way
        # to check what errors were already raised.
        media_type = validate_media_type(self.media_type)
        validate_asset_name_with_media_type(self.name, media_type)


class Asset(AssetBase):

    class Meta:
        unique_together = (('item', 'name'),)
        ordering = ['id']
        triggers = generates_asset_triggers()

    item = models.ForeignKey(
        Item,
        related_name='assets',
        related_query_name='asset',
        on_delete=models.PROTECT,
        help_text=_(SEARCH_TEXT_HELP_ITEM)
    )
    # From v1 on the json representation of this field changed from "eo:gsd" to "gsd". The two names
    # may be used interchangeably for a now.
    eo_gsd = models.FloatField(null=True, blank=True, validators=[validate_eo_gsd])

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

    # whether this asset is hosted externally
    is_external = models.BooleanField(
        default=False,
        help_text=_("Whether this asset is hosted externally")
    )

    def get_collection(self):
        return self.item.collection

    def get_asset_path(self):
        return get_asset_path(self.item, self.name)


class CollectionAsset(AssetBase):

    class Meta:
        unique_together = (('collection', 'name'),)
        ordering = ['id']
        triggers = generate_collection_asset_triggers()

    collection = models.ForeignKey(
        Collection,
        related_name='assets',
        related_query_name='asset',
        on_delete=models.PROTECT,
        help_text=_(SEARCH_TEXT_HELP_ITEM)
    )

    # CollectionAssets are never external
    is_external = False

    def get_collection(self):
        return self.collection

    def get_asset_path(self):
        return get_collection_asset_path(self.collection, self.name)


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
        triggers = generates_asset_upload_triggers()

    class Status(models.TextChoices):
        # pylint: disable=invalid-name
        IN_PROGRESS = 'in-progress'
        COMPLETED = 'completed'
        ABORTED = 'aborted'
        __empty__ = ''

    class ContentEncoding(models.TextChoices):
        # pylint: disable=invalid-name
        GZIP = 'gzip'
        BR = 'br'
        # DEFLATE = 'deflate'
        # COMPRESS = 'compress'
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
    md5_parts = models.JSONField(encoder=DjangoJSONEncoder, editable=False)
    urls = models.JSONField(default=list, encoder=DjangoJSONEncoder, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    ended = models.DateTimeField(blank=True, null=True, default=None)
    # From v1 on the json representation of this field changed from "checksum:multihash" to
    # "file:checksum". The two names may be used interchangeably for a now.
    checksum_multihash = models.CharField(max_length=255, blank=False, null=False)

    # NOTE: hidden ETag field, this field is automatically updated by stac_api.pgtriggers
    etag = models.CharField(blank=False, null=False, max_length=56, default=compute_etag)

    update_interval = models.IntegerField(
        default=-1,
        null=False,
        blank=False,
        validators=[MinValueValidator(-1)],
        help_text="Interval in seconds in which the asset data is updated."
        "-1 means that the data is not on a regular basis updated."
        "This field can only be set via the API."
    )

    content_encoding = models.CharField(
        choices=ContentEncoding.choices, blank=True, null=False, max_length=32, default=''
    )

    # Custom Manager that preselects the collection
    objects = AssetUploadManager()

    def update_asset_from_upload(self):
        '''Updating the asset's file:checksum and update_interval from the upload

        When the upload is completed, the new file:checksum and update interval from the upload
        is set to its asset parent.
        '''
        logger.debug(
            'Updating asset %s file:checksum from %s to %s and update_interval from %d to %d '
            'due to upload complete',
            self.asset.name,
            self.asset.checksum_multihash,
            self.checksum_multihash,
            self.asset.update_interval,
            self.update_interval,
            extra={
                'upload_id': self.upload_id,
                'asset': self.asset.name,
                'item': self.asset.item.name,
                'collection': self.asset.item.collection.name
            }
        )

        self.asset.checksum_multihash = self.checksum_multihash
        self.asset.update_interval = self.update_interval
        self.asset.save()
