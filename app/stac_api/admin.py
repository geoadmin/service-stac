from django.contrib import admin

from .models import Asset
from .models import Collection
from .models import Item

# Register your models here.

admin.site.register(Collection)
admin.site.register(Item)
admin.site.register(Asset)
