from admin_auto_filters.filters import AutocompleteFilter
from admin_auto_filters.filters import AutocompleteFilterFactory

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
from stac_api.utils import get_query_params


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

    class Media:
        js = ('js/admin/collection_help_search.js',)
        css = {'all': ('style/hover.css',)}

    fields = [
        'name',
        'title',
        'description',
        'extent_start_datetime',
        'extent_end_datetime',
        'summaries',
        'extent_geometry'
    ]
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


@admin.register(Item)
class ItemAdmin(admin.GeoModelAdmin):

    class Media:
        js = ('js/admin/item_help_search.js',)
        css = {'all': ('style/hover.css',)}

    inlines = [ItemLinkInline]
    autocomplete_fields = ['collection']
    search_fields = ['name', 'collection__name']
    readonly_fields = ['collection_name']
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
            fields[0][1]['fields'] = ('name', 'collection')
            return fields
        # Otherwise if this is an update operation only display the read only field
        # without help text
        fields[0][1]['fields'] = ('name', 'collection_name')
        return fields


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):

    class Media:
        js = ('js/admin/asset_help_search.js',)
        css = {'all': ('style/hover.css',)}

    autocomplete_fields = ['item']
    search_fields = ['name', 'item__name', 'item__collection__name']
    readonly_fields = ['item_name', 'collection_name', 'href', 'checksum_multihash']
    list_display = ['name', 'item_name', 'collection_name']
    fieldsets = (
        (None, {
            'fields': ('name', 'item')
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
            fields[0][1]['fields'] = ('name', 'item')
            return fields
        # Otherwise if this is an update operation only display the read only fields
        # without help text
        fields[0][1]['fields'] = ('name', 'item_name', 'collection_name')
        return fields
