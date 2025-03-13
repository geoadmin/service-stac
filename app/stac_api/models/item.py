import logging

from django.contrib.gis.db import models
from django.core.validators import MinValueValidator
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from stac_api.managers import ItemManager
from stac_api.models.collection import Collection
from stac_api.models.general import BBOX_CH
from stac_api.models.general import SEARCH_TEXT_HELP_ITEM
from stac_api.models.general import AssetBase
from stac_api.models.general import BaseAssetUpload
from stac_api.models.general import Link
from stac_api.models.general import compute_etag
from stac_api.pgtriggers import child_triggers
from stac_api.pgtriggers import generates_asset_triggers
from stac_api.pgtriggers import generates_asset_upload_triggers
from stac_api.pgtriggers import generates_item_triggers
from stac_api.utils import get_asset_path
from stac_api.validators import validate_eo_gsd
from stac_api.validators import validate_expires
from stac_api.validators import validate_geoadmin_variant
from stac_api.validators import validate_geometry
from stac_api.validators import validate_item_properties_datetimes
from stac_api.validators import validate_name

logger = logging.getLogger(__name__)

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
            # forecast properties are "queryable" in the search endpoint
            models.Index(
                fields=['forecast_reference_datetime'], name='item_fc_reference_datetime_idx'
            ),
            models.Index(fields=['forecast_horizon'], name='item_fc_horizon_idx'),
            models.Index(fields=['forecast_duration'], name='item_fc_duration_idx'),
            models.Index(fields=['forecast_variable'], name='item_fc_variable_idx'),
            models.Index(fields=['forecast_perturbed'], name='item_fc_perturbed_idx'),
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
    properties_expires = models.DateTimeField(
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

    total_data_size = models.BigIntegerField(default=0, null=True, blank=True)

    forecast_reference_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The reference datetime: i.e. predictions for times after "
        "this point occur in the future. Predictions prior to this "
        "time represent 'hindcasts', predicting states that have "
        "already occurred. This must be in UTC. It is formatted like "
        "'2022-08-12T00:00:00Z'."
    )

    forecast_horizon = models.DurationField(
        null=True,
        blank=True,
        help_text="The time between the reference datetime and the forecast datetime."
        "Formatted as ISO 8601 duration, e.g. 'PT6H' for a 6-hour forecast.",
    )

    forecast_duration = models.DurationField(
        null=True,
        blank=True,
        help_text="If the forecast is not only for a specific instance in time "
        "but instead is for a certain period, you can specify the "
        "length here. Formatted as ISO 8601 duration, e.g. 'PT3H' for a 3-hour "
        "accumulation. If not given, assumes that the forecast is for an "
        "instance in time as if this was set to PT0S (0 seconds).",
    )

    forecast_variable = models.CharField(
        null=True,
        blank=True,
        help_text="Name of the model variable that corresponds to the data. The variables "
        "should correspond to the CF Standard Names, "
        "e.g. `air_temperature` for the air temperature."
    )

    forecast_perturbed = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text="Denotes whether the data corresponds to the control run (`false`) or "
        "perturbed runs (`true`). The property needs to be specified in both "
        "cases as no default value is specified and as such the meaning is "
        "\"unknown\" in case it's missing."
    )

    # Custom Manager that preselects the collection
    objects = ItemManager()

    def __str__(self):
        # This is used in the admin page in the autocomplete_fields of the Asset page
        return f"{self.collection.name}/{self.name}"

    def clean(self):
        validate_item_properties_datetimes(
            self.properties_datetime,
            self.properties_start_datetime,
            self.properties_end_datetime,
        )
        validate_expires(self.properties_expires)


class ItemLink(Link):
    item = models.ForeignKey(
        Item, related_name='links', related_query_name='link', on_delete=models.CASCADE
    )

    class Meta:
        unique_together = (('rel', 'item'),)
        ordering = ['pk']
        triggers = child_triggers('item', 'ItemLink')


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


class AssetUpload(BaseAssetUpload):

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

    asset = models.ForeignKey(Asset, related_name='+', on_delete=models.CASCADE)

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
        self.asset.file_size = self.file_size
        self.asset.save()
