from django.contrib import admin

# Register your models here.

from .models import Collection, Item, Asset

admin.site.register(Collection)
admin.site.register(Item)
admin.site.register(Asset)