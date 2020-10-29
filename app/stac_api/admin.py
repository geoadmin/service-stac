from django.contrib import admin

from .models import Asset
from .models import Collection
from .models import Item
from .models import Provider
from .models import Keyword
from .models import CollectionLink
from .models import ItemLink

# Register your models here.

admin.site.register(Collection)
admin.site.register(Item)
admin.site.register(Asset)
admin.site.register(Provider)
admin.site.register(Keyword)
admin.site.register(CollectionLink)
admin.site.register(ItemLink)
