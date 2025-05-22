import hashlib
import logging
import os
import time
from uuid import uuid4

from language_tags import tags
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
from django.db.models.deletion import ProtectedError
from django.utils.translation import gettext_lazy as _

from stac_api.managers import AssetUploadManager
from stac_api.pgtriggers import child_triggers
from stac_api.utils import select_s3_bucket
from stac_api.validators import MEDIA_TYPES
from stac_api.validators import validate_asset_name
from stac_api.validators import validate_asset_name_with_media_type
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
    hreflang = models.CharField(blank=True, null=True, max_length=32)

    class Meta:
        abstract = True

    def __str__(self):
        return f'{self.rel}: {self.href}'

    def save(self, *args, **kwargs) -> None:
        """Validate the hreflang"""
        self.full_clean()

        if self.hreflang is not None and self.hreflang != '' and not tags.check(self.hreflang):
            raise ValidationError(_(", ".join([v.message for v in tags.tag(self.hreflang).errors])))

        super().save(*args, **kwargs)


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
        triggers = child_triggers('collection', 'Provider')

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


ITEM_KEEP_ORIGINAL_FIELDS = [
    'geometry',
    'properties_datetime',
    'properties_start_datetime',
    'properties_end_datetime',
]


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
    # Same here for the cache_control_header that is used by the storages.S3Storage to set the
    # asset's cache control header during upload
    instance.file.storage.cache_control_header = instance.get_collection().cache_control_header
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
    instance.file_size = instance.file.size
    return instance.get_asset_path()


class DynamicStorageFileField(models.FileField):

    # Beware! The current implementation changes the storage for all model instances that use
    # this field. It may happen that reading a file size, for example, will attend to read from
    # the wrong bucket if another model instance has uploaded something to a different bucket
    # before. See PB-1669.

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
        "upload."
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
        help_text="<b>DEPRECATED FIELD, has no effect anymore. </b></br>"
        "Interval in seconds in which the asset data is updated. "
        "-1 means that the data is not on a regular basis updated."
    )

    # Depending on the value here we can determine some state of the asset:
    # * None: The asset was created but the file doesn't actually exist on
    #         the referenced bucket. This was determined in a one-off check run in
    #         2025, see PB-1091
    # * 0:    The asset was created, but the file has not yet been uploaded
    # * -1:   This is an external asset, thus we write -1 as we can't yet determine
    #         the file size of external assets
    file_size = models.BigIntegerField(default=0, null=True, blank=True)

    def __str__(self):
        return self.name

    def get_asset_path(self):
        # Method must be implemented by Asset and CollectionAsset separately.
        raise NotImplementedError("get_asset_path() not implemented")

    def save(self, *args, **kwargs):
        # Default file value to the asset path.
        #
        # This is the behaviour when creating an asset via PUT API endpoint.
        # But we need to set this here so it also applies in the admin UI.
        if not bool(self.file):
            self.file = self.get_asset_path()
        super().save(*args, **kwargs)

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


class BaseAssetUpload(models.Model):

    class Meta:
        abstract = True

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
        help_text="<b>DEPRECATED FIELD, has no effect anymore. </b></br>"
        "Interval in seconds in which the asset data is updated. "
        "-1 means that the data is not on a regular basis updated. "
        "This field can only be set via the API."
    )

    file_size = models.BigIntegerField(default=0, null=True, blank=True)

    content_encoding = models.CharField(
        choices=ContentEncoding.choices, blank=True, null=False, max_length=32, default=''
    )

    # Custom Manager that preselects the collection
    objects = AssetUploadManager()
