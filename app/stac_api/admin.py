from django.contrib.gis import admin
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

admin.site.register(Asset)


class LandingPageLinkInline(admin.TabularInline):
    model = LandingPageLink
    extra = 0


@admin.register(LandingPage)
class LandingPageAdmin(SingletonModelAdmin):
    inlines = [LandingPageLinkInline]


@admin.register(ConformancePage)
class ConformancePageAdmin(SingletonModelAdmin):
    model = ConformancePage
    extra = 0


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


class ItemLinkInline(admin.TabularInline):
    model = ItemLink
    extra = 0


@admin.register(Item)
class ItemAdmin(admin.GeoModelAdmin):
    inlines = [ItemLinkInline]
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
    # customisation of the geometry field
    map_template = finders.find('admin/ol_swisstopo.html')  # custom swisstopo
    wms_layer = 'ch.swisstopo.pixelkarte-farbe-pk1000.noscale'
    wms_url = 'https://wms.geo.admin.ch/'
