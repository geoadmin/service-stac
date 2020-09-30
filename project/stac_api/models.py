from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

# pylint: disable=fixme
# TODO remove this pylint disable once this is done

# st_geometry bbox ch
BBOX_CH = 'POLYGON((2317000 913000,3057000 913000,3057000 1413000,2317000 1413000,2317000 913000))'

# I allowed myself to make excessive use of comments below, as this is still work in progress.
# all the comments can be deleted later on


class Collection(models.Model):
    crs = models.URLField(default="http://www.opengis.net/def/crs/OGC/1.3/CRS84")
    # bgid_id = models.BigAutoField(primary_key=True, editable=False) # not sure, if we need this field. The "id" field below should do the joc.
    # if we need bgid anyways, will it be auto-generated, or should we use the geocat_uuid here?
    # for using the geocat_uuid: models.UUIDField(primary_key=True,editable=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    description = models.TextField(blank=False)  # blank=False means this field is required
    # extent will be a JSONField containing an object "temporal" with an arry "bbox" of the bounding coordinates
    # and an object "temporal" with an arry "interval" consisting of a start and end date.
    # Formating/Meaning of those dates see: https://github.com/radiantearth/stac-spec/blob/v0.9.0/collection-spec/collection-spec.md#temporal-extent-object
    # TODO: in sqlite3 the JSON1 extension must be enabled for using JSONFields: https://code.djangoproject.com/wiki/JSON1Extension
    extent = models.JSONField(blank=False)
    collection_id = models.TextField(
        primary_key=True, editable=False
    )  # this is what is simply only called "id" in here: http://ltboc.infra.bgdi.ch/static/products/data.geo.admin.ch/apitransactional.html#operation/createCollection
    itemType = models.TextField(default="Feature")
    keywords = models.JSONField()  # containing an array of strings
    license = models.TextField(blank=False)
    links = models.JSONField(
        blank=False
    )  # containing an array of objects (Links (self, root and item), each with "href" and "rel"
    providers = models.JSONField(
    )  # containing an array of objects (providers, each with "name", "roles" and "url")
    stac_extensions = models.JSONField()  # array of reference to a JSON schema or core extension
    stac_version = models.TextField(blank=False)
    summaries = models.JSONField(
    )  # this is, where some of the geocat-data could go. So this should contain "eo:gsd", "geoadmin:variant" and "proj:epsg"
    title = models.TextField()


class Item(models.Model):
    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE
    )  # models.CASCADE means: when a collection is deleted, all items in it will also be deleted
    bbox = models.JSONField(blank=False)  # can be 2D or 3D
    geometry = models.JSONField(blank=False)  # this will a GeoJSON Geometry objerct
    item_id = models.TextField(primary_key=True, blank=False)
    links = models.JSONField(
        blank=False
    )  # containing an array of objects (Links (self, root and item), each with "href" and "rel"
    properties = models.JSONField(
        blank=False
    )  # core metadata (e.g. datetime, eo:bands, eo:cloud_cover, eo:gsd, ...) fields plus extensions
    stac_extensions = models.JSONField()
    stac_version = models.TextField(blank=False)
    GeoJSON_type = models.TextField(
        default="Feature", blank=False, editable=False
    )  # specifies the GeoJSON type and MUST be set to "Feature". Guess there is a more elegant way to prescribe a fixed value
    # other than giving a default value and don't allow editing.
    assets = models.JSONField(
    )  # this is defined as required here: https://github.com/radiantearth/stac-spec/blob/v0.9.0/item-spec/item-spec.md
    # and is meant to contain a dictionary of asset objects than can be downloaded, each with a unique key
    location = models.URLField()


class Asset(models.Model):
    feature_id = models.ForeignKey(Item, on_delete=models.CASCADE)
    # TODO: define a field "collection" that references to the collection to which the parent-item belongs to.

    @property
    def collection(self):
        return self.feature_id.collection

    asset_id = models.TextField(primary_key=True, blank=False)
    checksum_multihash = models.TextField(blank=False)
    description = models.TextField()
    eo_gsd = models.FloatField()

    class language(models.TextChoices):
        GERMAN = 'de', _('German')
        ITALIAN = 'it', _('Italian')
        FRENCH = 'fr', _('French')
        ROMANSH = 'rm', _('Romansh')
        ENGLISH = 'en', _('English')
        NONE = '', _('')

    geoadmin_lang = models.TextField(max_length=2, choices=language.choices, default=language.NONE)
    geoadmin_variant = models.TextField()
    proj = models.IntegerField(null=True)
    title = models.TextField()
    media_type = models.TextField()
    copyFromHref = models.URLField()
    location = models.URLField()
