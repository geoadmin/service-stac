import json
import logging

from admin_auto_filters.filters import AutocompleteFilter
from admin_auto_filters.filters import AutocompleteFilterFactory

from django import forms
from django.contrib import messages
from django.contrib.gis import admin
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.db.models.deletion import ProtectedError
from django.forms import CharField
from django.forms import Textarea
from django.http import HttpResponseRedirect
from django.urls import reverse

from solo.admin import SingletonModelAdmin

from stac_api.models import BBOX_CH
from stac_api.models import Asset
from stac_api.models import AssetUpload
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import ConformancePage
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import LandingPage
from stac_api.models import LandingPageLink
from stac_api.models import Provider
from stac_api.utils import build_asset_href
from stac_api.utils import get_query_params
from stac_api.validators import validate_text_to_geometry

logger = logging.getLogger(__name__)


class LandingPageLinkInline(admin.TabularInline):
    model = LandingPageLink
    extra = 0


@admin.register(LandingPage)
class LandingPageAdmin(SingletonModelAdmin):
    inlines = [LandingPageLinkInline]


@admin.register(ConformancePage)
class ConformancePageAdmin(SingletonModelAdmin):
    formfield_overrides = {
        ArrayField: {
            'widget': Textarea(attrs={
                'rows': 10, 'cols': 60
            })
        },
    }


class ProviderInline(admin.TabularInline):
    model = Provider
    extra = 0
    formfield_overrides = {
        models.TextField: {
            'widget': Textarea(attrs={
                'rows': 4, 'cols': 40
            }),
            'empty_value': None,
        },
    }


class CollectionLinkInline(admin.TabularInline):
    model = CollectionLink
    extra = 0


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):

    class Media:
        js = ('js/admin/collection_help_search.js',)
        css = {'all': ('style/hover.css',)}

    fields = [
        'name',
        'published',
        'title',
        'description',
        'created',
        'updated',
        'extent_start_datetime',
        'extent_end_datetime',
        'extent_geometry',
        'summaries_proj_epsg',
        'summaries_geoadmin_variant',
        'summaries_geoadmin_lang',
        'summaries_eo_gsd',
        'license',
        'etag'
    ]
    readonly_fields = [
        'extent_start_datetime',
        'extent_end_datetime',
        'extent_geometry',
        'created',
        'updated',
        'summaries_proj_epsg',
        'summaries_geoadmin_variant',
        'summaries_geoadmin_lang',
        'summaries_eo_gsd',
        'etag'
    ]
    inlines = [ProviderInline, CollectionLinkInline]
    search_fields = ['name']
    list_display = ['name', 'published']
    list_filter = ['published']

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term.startswith('"') and search_term.endswith('"'):
            queryset |= self.model.objects.filter(name__exact=search_term.strip('"'))
        return queryset, use_distinct

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return self.readonly_fields + ['name']
        return self.readonly_fields


class ItemLinkInline(admin.TabularInline):
    model = ItemLink
    extra = 0


class CollectionFilterForItems(AutocompleteFilter):
    title = 'Collection name'  # display title
    field_name = 'collection'  # name of the foreign key


# helper form to add an extra text_geometry field to ItemAdmin
class ItemAdminForm(forms.ModelForm):
    help_text = """Insert either:<br/>
    - An extent in either WGS84 or LV95: "xmin, ymin, xmax, ymax"
    where x is easting and y is northing<br/>
    - A WKT polygon.
    F.ex. "SRID=4326;POLYGON((5.96 45.82, 5.96 47.81, 10.49 47.81, 10.49 45.82, 5.96 45.82))"
    <br/><br/><b>In any case the geometry will be saved as a WKT POLYGON in WGS84.</b>
    """
    text_geometry = CharField(
        label='Geometry text', widget=forms.TextInput(attrs={'size': 150}), help_text=help_text
    )

    def clean_text_geometry(self):
        # validating and transforming the text to a geometry
        self.cleaned_data["text_geometry"] = validate_text_to_geometry(self.data["text_geometry"])
        return self.cleaned_data["text_geometry"]


@admin.register(Item)
class ItemAdmin(admin.GeoModelAdmin):
    form = ItemAdminForm
    modifiable = False

    class Media:
        js = ('js/admin/item_help_search.js',)
        css = {'all': ('style/hover.css',)}

    inlines = [ItemLinkInline]
    autocomplete_fields = ['collection']
    search_fields = ['name', 'collection__name']
    readonly_fields = ['collection_name', 'created', 'updated', 'etag']
    fieldsets = (
        (None, {
            'fields': ('name', 'collection', 'created', 'updated', 'etag')
        }),
        ('geometry', {
            'fields': (
                'geometry',
                'text_geometry',
            ),
        }),
        (
            'Properties',
            {
                'fields': (
                    'properties_datetime',
                    'properties_start_datetime',
                    'properties_end_datetime',
                    'properties_title'
                )
            }
        ),
    )

    list_display = ['name', 'collection', 'collection_published']
    list_filter = [CollectionFilterForItems]

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        # The following few lines are a bit hacky and are needed for the item dropdown list
        # to depend on the currently selected collection in the collection dropdown filter.
        # With this "hack", only those items appear in the "filter by item name" dropdown list,
        # that belong to the currently selected collection in the "filter by collection name"
        # dropdown list. Otherwise all items would appear in the dropdown list, which does not
        # make sense.

        # this asserts that the request comes from the autocomplete filters.
        if request.path.endswith("/autocomplete/"):
            collection_filter_param = get_query_params(
                request.headers['Referer'], 'item__collection'
            )
            if collection_filter_param:
                queryset = queryset.filter(collection__pk__exact=collection_filter_param[0])
        if search_term.startswith('"') and search_term.endswith('"'):
            search_terms = search_term.strip('"').split('/', maxsplit=2)
            if len(search_terms) == 2:
                collection_name = search_terms[0]
                item_name = search_terms[1]
            else:
                collection_name = None
                item_name = search_terms[0]
            queryset |= self.model.objects.filter(name__exact=item_name)
            if collection_name:
                queryset &= self.model.objects.filter(collection__name__exact=collection_name)
        return queryset, use_distinct

    def collection_published(self, instance):
        return instance.collection.published

    collection_published.admin_order_field = 'collection__published'
    collection_published.short_description = 'Published'
    collection_published.boolean = True

    # Here we use a special field for read only to avoid adding the extra help text for search
    # functionality
    def collection_name(self, obj):
        return obj.collection.name

    collection_name.admin_order_field = 'collection__name'
    collection_name.short_description = 'Collection Id'

    # We don't want to move the assets on S3
    # That's why some fields like the name of the item and the collection name are set readonly here
    # for update operations. Those fields value are used as key on S3 that's why renaming them
    # would mean that the Asset on S3 should be moved.
    def get_fieldsets(self, request, obj=None):
        fields = super().get_fieldsets(request, obj)
        if obj is None:
            # In case a new Item is added use the normal field 'collection' from model that have
            # a help text fort the search functionality.
            fields[0][1]['fields'] = ('name', 'collection', 'created', 'updated', 'etag')
            return fields
        # Otherwise if this is an update operation only display the read only field
        # without help text
        fields[0][1]['fields'] = ('name', 'collection_name', 'created', 'updated', 'etag')
        return fields

    # Populate text_geometry field with value of geometry
    def get_form(self, request, obj=None, **kwargs):  # pylint: disable=arguments-differ
        # pylint: disable=attribute-defined-outside-init
        form = super().get_form(request, obj, **kwargs)
        if obj is not None:
            form.base_fields['text_geometry'].initial = obj.geometry
        else:
            form.base_fields['text_geometry'].initial = BBOX_CH
        return form

    # Overwrite value of geometry with value of text_geometry
    def save_model(self, request, obj, form, change):
        obj.geometry = form.cleaned_data['text_geometry']
        return super().save_model(request, obj, form, change)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):

    class Media:
        js = ('js/admin/asset_help_search.js',)
        css = {'all': ('style/hover.css',)}

    autocomplete_fields = ['item']
    search_fields = ['name', 'item__name', 'item__collection__name']
    readonly_fields = [
        'item_name', 'collection_name', 'href', 'checksum_multihash', 'created', 'updated', 'etag'
    ]
    list_display = ['name', 'item_name', 'collection_name', 'collection_published']
    fieldsets = (
        (None, {
            'fields': ('name', 'item', 'created', 'updated', 'etag')
        }),
        ('File', {
            'fields': ('file', 'media_type', 'href', 'checksum_multihash')
        }),
        ('Description', {
            'fields': ('title', 'description')
        }),
        ('Attributes', {
            'fields': ('eo_gsd', 'proj_epsg', 'geoadmin_variant', 'geoadmin_lang')
        }),
    )
    list_filter = [
        AutocompleteFilterFactory('Item name', 'item', use_pk_exact=True),
        AutocompleteFilterFactory('Collection name', 'item__collection', use_pk_exact=True)
    ]

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term.startswith('"') and search_term.endswith('"'):
            search_terms = search_term.strip('"').split('/', maxsplit=3)
            if len(search_terms) == 3:
                collection_name = search_terms[0]
                item_name = search_terms[1]
                asset_name = search_terms[2]
            elif len(search_terms) == 2:
                collection_name = None
                item_name = search_terms[0]
                asset_name = search_terms[1]
            else:
                collection_name = None
                item_name = None
                asset_name = search_terms[0]
            queryset |= self.model.objects.filter(name__exact=asset_name)
            if item_name:
                queryset &= self.model.objects.filter(item__name__exact=item_name)
            if collection_name:
                queryset &= self.model.objects.filter(item__collection__name__exact=collection_name)
        return queryset, use_distinct

    def collection_published(self, instance):
        return instance.item.collection.published

    collection_published.admin_order_field = 'item__collection__published'
    collection_published.short_description = 'Published'
    collection_published.boolean = True

    def collection_name(self, instance):
        return instance.item.collection.name

    collection_name.admin_order_field = 'item__collection__name'
    collection_name.short_description = 'Collection Id'

    def item_name(self, instance):
        return instance.item.name

    item_name.admin_order_field = 'item__name'
    item_name.short_description = 'Item Id'

    def save_model(self, request, obj, form, change):
        if obj.description == '':
            # The admin interface with TextArea uses empty string instead
            # of None. We use None for empty value, None value are stripped
            # then in the output will empty string not.
            obj.description = None

        super().save_model(request, obj, form, change)

    # Note: this is a bit hacky and only required to get access
    # to the request object in 'href' method.
    def get_form(self, request, obj=None, **kwargs):  # pylint: disable=arguments-differ
        self.request = request  # pylint: disable=attribute-defined-outside-init
        return super().get_form(request, obj, **kwargs)

    def href(self, instance):
        path = instance.file.name
        return build_asset_href(self.request, path)

    # We don't want to move the assets on S3
    # That's why some fields like the name of the asset are set readonly here
    # for update operations
    def get_fieldsets(self, request, obj=None):
        fields = super().get_fieldsets(request, obj)
        if obj is None:
            # In case a new Asset is added use the normal field 'item' from model that have
            # a help text fort the search functionality.
            fields[0][1]['fields'] = ('name', 'item', 'created', 'updated', 'etag')
            return fields
        # Otherwise if this is an update operation only display the read only fields
        # without help text
        fields[0][1]['fields'] = (
            'name', 'item_name', 'collection_name', 'created', 'updated', 'etag'
        )
        return fields


@admin.register(AssetUpload)
class AssetUploadAdmin(admin.ModelAdmin):

    autocomplete_fields = ['asset']
    search_fields = [
        'upload_id', 'asset__name', 'asset__item__name', 'asset__item__collection__name', 'status'
    ]
    readonly_fields = [
        'upload_id',
        'asset_name',
        'item_name',
        'collection_name',
        'created',
        'ended',
        'etag',
        'status',
        'urls_json',
        'number_parts',
        'checksum_multihash'
    ]
    list_display = [
        'short_upload_id', 'status', 'asset_name', 'item_name', 'collection_name', 'created'
    ]
    fieldsets = (
        (None, {
            'fields': ('upload_id', 'asset_name', 'item_name', 'collection_name', 'status')
        }),
        (
            'Attributes', {
                'fields': ('number_parts', 'urls_json', 'checksum_multihash', 'created', 'ended')
            }
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def short_upload_id(self, instance):
        if len(instance.upload_id) > 32:
            return instance.upload_id[:29] + '...'
        return instance.upload_id

    short_upload_id.admin_order_field = 'upload_id'
    short_upload_id.short_description = 'Upload ID'

    def collection_name(self, instance):
        return instance.asset.item.collection.name

    collection_name.admin_order_field = 'asset__item__collection__name'
    collection_name.short_description = 'Collection Id'

    def item_name(self, instance):
        return instance.asset.item.name

    item_name.admin_order_field = 'asset__item__name'
    item_name.short_description = 'Item Id'

    def asset_name(self, instance):
        return instance.asset.name

    asset_name.admin_order_field = 'asset__name'
    asset_name.short_description = 'Asset Id'

    def urls_json(self, instance):
        return json.dumps(instance.urls, indent=1)

    urls_json.short_description = "Urls"

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except ProtectedError:
            msg = "You cannot delete Asset Upload that are in progress"
            self.message_user(request, msg, messages.ERROR)
            opts = self.model._meta
            return_url = reverse(
                f'admin:{opts.app_label}_{opts.model_name}_change',
                args=(object_id,),
                current_app=self.admin_site.name,
            )
            return HttpResponseRedirect(return_url)
