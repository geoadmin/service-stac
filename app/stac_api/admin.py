from django.conf import settings
from django.contrib.gis import admin
from django.contrib.staticfiles import finders
from django.db import models
from django.forms import Textarea

from solo.admin import SingletonModelAdmin

from .models import Asset
from .models import Collection
from .models import CollectionLink
from .models import Item
from .models import ItemLink
from .models import LandingPage
from .models import LandingPageLink
from .models import Provider

admin.site.register(Asset)


class LandingPageLinkInline(admin.TabularInline):
    model = LandingPageLink
    extra = 0


@admin.register(LandingPage)
class LandingPageAdmin(SingletonModelAdmin):
    inlines = [LandingPageLinkInline]


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
    readonly_fields = ['cache_start_datetime', 'cache_end_datetime', 'summaries', 'extent_geometry']
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
    if settings.APP_ENV == 'local':
        wms_layer = 'ch.swisstopo.pixelkarte-farbe-pk1000.noscale'
        wms_url = 'https://wms.geo.admin.ch/'
    else:
        wms_layer = 'ch.swisstopo.pixelkarte-farbe'
