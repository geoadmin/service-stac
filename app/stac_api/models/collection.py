import logging

from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MinValueValidator
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from stac_api.models.general import SEARCH_TEXT_HELP_ITEM
from stac_api.models.general import AssetBase
from stac_api.models.general import BaseAssetUpload
from stac_api.models.general import Link
from stac_api.models.general import compute_etag
from stac_api.pgtriggers import SummaryFields
from stac_api.pgtriggers import child_triggers
from stac_api.pgtriggers import generates_asset_upload_triggers
from stac_api.pgtriggers import generates_collection_asset_triggers
from stac_api.pgtriggers import generates_collection_triggers
from stac_api.pgtriggers import generates_summary_count_triggers
from stac_api.utils import get_collection_asset_path
from stac_api.validators import validate_cache_control_header
from stac_api.validators import validate_name

logger = logging.getLogger(__name__)


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
    # Set to true if the extent needs to be recalculated.
    extent_out_of_sync = models.BooleanField(default=False)
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

    total_data_size = models.BigIntegerField(default=0, null=True, blank=True)

    allow_external_assets = models.BooleanField(
        default=False,
        help_text=_('Whether this collection can have assets that are hosted externally')
    )

    external_asset_whitelist = ArrayField(
        models.CharField(max_length=255), blank=True, default=list,
        help_text=_('Provide a comma separated list of '
                    'protocol://domain values for the external asset url validation')
    )

    cache_control_header = models.CharField(
        max_length=255, blank=True, null=True,
        validators=[validate_cache_control_header],
        help_text=_(
            'Cache-Control header value to use for this collection. When set it override the '
            'default cache control header value for all API call related to the collection as well '
            'as for the data download call.'
        )
    )

    def __str__(self):
        return self.name


class CollectionLink(Link):
    collection = models.ForeignKey(
        Collection, related_name='links', related_query_name='link', on_delete=models.CASCADE
    )

    class Meta:
        ordering = ['pk']
        triggers = child_triggers('collection', 'CollectionLink')


class CollectionAsset(AssetBase):

    class Meta:
        unique_together = (('collection', 'name'),)
        ordering = ['id']
        triggers = generates_collection_asset_triggers()


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


class CollectionAssetUpload(BaseAssetUpload):

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['asset', 'upload_id'],
                name='unique_asset_upload_collection_asset_upload_id'
            ),
            # Make sure that there is only one upload in progress per collection asset
            models.UniqueConstraint(
                fields=['asset', 'status'],
                condition=Q(status='in-progress'),
                name='unique_asset_upload_in_progress'
            )
        ]
        triggers = generates_asset_upload_triggers()

    asset = models.ForeignKey(CollectionAsset, related_name='+', on_delete=models.CASCADE)

    def update_asset_from_upload(self):
        '''Updating the asset's file:checksum and update_interval from the upload

        When the upload is completed, the new file:checksum and update interval from the upload
        is set to its asset parent.
        '''
        logger.debug(
            'Updating collection asset %s file:checksum from %s to %s and update_interval '
            'from %d to %d due to upload complete',
            self.asset.name,
            self.asset.checksum_multihash,
            self.checksum_multihash,
            self.asset.update_interval,
            self.update_interval,
            extra={
                'upload_id': self.upload_id,
                'asset': self.asset.name,
                'collection': self.asset.collection.name
            }
        )

        self.asset.checksum_multihash = self.checksum_multihash
        self.asset.update_interval = self.update_interval
        self.asset.file_size = self.file_size
        self.asset.save()


class CountBase(models.Model):
    '''CountBase tables are used to help calculate the summary on a collection.
    This is only performant if the distinct number of values is small, e.g. we currently only have
    5 possible values for geoadmin_language.
    For each assets value we keep a count of how often that value exists, per collection. On
    insert/update/delete of an asset we only need to decrease and/or increase the counter value.
    Since the number of possible values is small, the aggregate array calculation to update the
    collection also stays performant.
    '''

    class Meta:
        abstract = True

    id = models.BigAutoField(primary_key=True)
    collection = models.ForeignKey(
        Collection,
        related_name='+',
        on_delete=models.CASCADE,
    )
    count = models.PositiveIntegerField(null=False)


class GSDCount(CountBase):
    # Update by asset triggers.

    class Meta:
        unique_together = (('collection', 'value'),)
        ordering = ['id']
        triggers = generates_summary_count_triggers(
            SummaryFields.GSD.value[0], SummaryFields.GSD.value[1]
        )

    value = models.FloatField(null=True, blank=True)


class GeoadminLangCount(CountBase):
    # Update by asset triggers.

    class Meta:
        unique_together = (('collection', 'value'),)
        ordering = ['id']
        triggers = generates_summary_count_triggers(
            SummaryFields.LANGUAGE.value[0], SummaryFields.LANGUAGE.value[1]
        )

    value = models.CharField(max_length=2, default=None, null=True, blank=True)


class GeoadminVariantCount(CountBase):
    # Update by asset triggers.

    class Meta:
        unique_together = (('collection', 'value'),)
        ordering = ['id']
        triggers = generates_summary_count_triggers(
            SummaryFields.VARIANT.value[0], SummaryFields.VARIANT.value[1]
        )

    value = models.CharField(max_length=25, null=True, blank=True)


class ProjEPSGCount(CountBase):
    # Update by asset and collection asset triggers.

    class Meta:
        unique_together = (('collection', 'value'),)
        ordering = ['id']
        triggers = generates_summary_count_triggers(
            SummaryFields.PROJ_EPSG.value[0], SummaryFields.PROJ_EPSG.value[1]
        )

    value = models.IntegerField(null=True, blank=True)
