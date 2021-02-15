from django.contrib.gis import admin
from django.contrib.postgres.fields import ArrayField
from django.contrib.staticfiles import finders
from django.db import models
from django.forms import Textarea

from solo.admin import SingletonModelAdmin

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import ConformancePage
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import LandingPage
from stac_api.models import LandingPageLink
from stac_api.models import Provider
from stac_api.utils import build_asset_href


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
            })
        },
    }


class CollectionLinkInline(admin.TabularInline):
    model = CollectionLink
    extra = 0


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    readonly_fields = [
        'extent_start_datetime', 'extent_end_datetime', 'summaries', 'extent_geometry'
    ]
    inlines = [ProviderInline, CollectionLinkInline]
    search_fields = ['name']
    list_display = ['name']

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term.startswith('"') and search_term.endswith('"'):
            queryset |= self.model.objects.filter(name__exact=search_term.strip('"'))
        return queryset, use_distinct


class ItemLinkInline(admin.TabularInline):
    model = ItemLink
    extra = 0


@admin.register(Item)
class ItemAdmin(admin.GeoModelAdmin):
    inlines = [ItemLinkInline]
    autocomplete_fields = ['collection']
    search_fields = ['name']
    fieldsets = (
        (None, {
            'fields': ('name', 'collection', 'geometry')
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
    # customization of the geometry field
    map_template = finders.find('admin/ol_swisstopo.html')  # custom swisstopo
    wms_layer = 'ch.swisstopo.pixelkarte-farbe-pk1000.noscale'
    wms_url = 'https://wms.geo.admin.ch/'
    list_display = ['name', 'collection']

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term.startswith('"') and search_term.endswith('"'):
            queryset |= self.model.objects.filter(name__exact=search_term.strip('"'))
        return queryset, use_distinct


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    autocomplete_fields = ['item']
    search_fields = ['name']
    readonly_fields = ['collection', 'href', 'checksum_multihash']
    list_display = ['name', 'item', 'collection']
    fieldsets = (
        (None, {
            'fields': ('name', 'item', 'collection')
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

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term.startswith('"') and search_term.endswith('"'):
            queryset |= self.model.objects.filter(name__exact=search_term.strip('"'))
        return queryset, use_distinct

    def collection(self, instance):
        return instance.item.collection

    collection.admin_order_field = 'item__collection'

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
