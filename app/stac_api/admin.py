from django.contrib import admin
from django.db import models
from django.forms import Textarea

from .models import Asset
from .models import Collection
from .models import CollectionLink
from .models import Item
from .models import ItemLink
from .models import Provider

admin.site.register(Item)
admin.site.register(Asset)
admin.site.register(CollectionLink)
admin.site.register(ItemLink)


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


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    inlines = [
        ProviderInline,
    ]
