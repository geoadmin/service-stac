import json
import logging

from admin_auto_filters.filters import AutocompleteFilter
from admin_auto_filters.filters import AutocompleteFilterFactory

from django import forms
from django.contrib import messages
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.utils import unquote
from django.contrib.gis import admin
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.db.models.deletion import ProtectedError
from django.forms import CharField
from django.forms import Textarea
from django.http import HttpResponseRedirect
from django.template.defaultfilters import filesizeformat
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from stac_api.models.collection import Collection
from stac_api.models.collection import CollectionAsset
from stac_api.models.collection import CollectionLink
from stac_api.models.general import BBOX_CH
from stac_api.models.general import LandingPage
from stac_api.models.general import LandingPageLink
from stac_api.models.general import Provider
from stac_api.models.item import Asset
from stac_api.models.item import AssetUpload
from stac_api.models.item import Item
from stac_api.models.item import ItemLink
from stac_api.utils import build_asset_href
from stac_api.utils import get_query_params
from stac_api.validators import validate_href_reachability
from stac_api.validators import validate_href_url
from stac_api.validators import validate_text_to_geometry

logger = logging.getLogger(__name__)


class LandingPageLinkInline(admin.TabularInline):
    model = LandingPageLink
    extra = 0


@admin.register(LandingPage)
class LandingPageAdmin(admin.ModelAdmin):
    inlines = [LandingPageLinkInline]
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


class LinkInline(admin.TabularInline):

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # make the hreflang field a bit shorter so that the inline
        # will not be rendered too wide
        if db_field.attname == 'hreflang':
            attrs = {'size': 10}
            kwargs['widget'] = forms.TextInput(attrs=attrs)
        return super().formfield_for_dbfield(db_field, request, **kwargs)


class CollectionLinkInline(LinkInline):
    model = CollectionLink
    extra = 0


class CollectionAssetInline(admin.StackedInline):
    model = CollectionAsset
    readonly_fields = [
        'file',
        'file_size',
    ]
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
        'etag',
        'displayed_total_data_size',
        'allow_external_assets',
        'external_asset_whitelist',
        'cache_control_header',
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
        'etag',
        'displayed_total_data_size'
    ]
    inlines = [ProviderInline, CollectionLinkInline, CollectionAssetInline]
    search_fields = ['name']
    list_display = ['name', 'published']
    list_filter = ['published']

    #helper function which displays the bytes in human-readable format
    def displayed_total_data_size(self, instance):
        return filesizeformat(instance.total_data_size)

    displayed_total_data_size.short_description = 'Total data size'

    def render_change_form(self, request, context, *args, **kwargs):
        form_instance = context['adminform'].form
        form_instance.fields['external_asset_whitelist'].widget = Textarea(
            attrs={
                'rows': 10,
                'cols': 60,
                'placeholder': 'https://map.geo.admin.ch,https://swisstopo.ch'
            }
        )

        return super().render_change_form(request, context, *args, **kwargs)

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term.startswith('"') and search_term.endswith('"'):
            queryset |= self.model.objects.filter(name__exact=search_term.strip('"'))
        return queryset, use_distinct

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return self.readonly_fields + ['name']
        return self.readonly_fields


class ItemLinkInline(LinkInline):
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
class ItemAdmin(admin.ModelAdmin):
    form = ItemAdminForm
    modifiable = False

    class Media:
        js = ('js/admin/item_help_search.js',)
        css = {'all': ('style/hover.css',)}

    inlines = [ItemLinkInline]
    autocomplete_fields = ['collection']
    search_fields = ['name', 'collection__name']
    readonly_fields = [
        'collection_name',
        'created',
        'updated',
        'etag',
        'displayed_total_data_size',
    ]
    fieldsets = (
        (
            None,
            {
                'fields': (
                    'name',
                    'collection',
                    'created',
                    'updated',
                    'etag',
                    'displayed_total_data_size',
                )
            }
        ),
        ('geometry', {
            'fields': ('geometry', 'text_geometry'),
        }),
        (
            'Properties',
            {
                'fields': (
                    'properties_datetime',
                    'properties_start_datetime',
                    'properties_end_datetime',
                    'properties_expires',
                    'properties_title'
                )
            }
        ),
        (
            'Forecast',
            {
                'fields': (
                    'forecast_reference_datetime',
                    'forecast_horizon',
                    'forecast_duration',
                    'forecast_variable',
                    'forecast_perturbed',
                )
            }
        ),
    )

    list_display = ['name', 'collection', 'collection_published']
    list_filter = [CollectionFilterForItems]

    #helper function which displays the bytes in human-readable format
    def displayed_total_data_size(self, instance):
        return filesizeformat(instance.total_data_size)

    displayed_total_data_size.short_description = 'Total data size'

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
            fields[0][1]['fields'] = (
                'name',
                'collection',
                'created',
                'updated',
                'etag',
                'displayed_total_data_size',
            )
            return fields
        # Otherwise if this is an update operation only display the read only field
        # without help text
        fields[0][1]['fields'] = (
            'name',
            'collection_name',
            'created',
            'updated',
            'etag',
            'displayed_total_data_size',
        )
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


class AssetUploadAdminMixin:
    upload_template_name = "uploadtemplate.html"
    url_suffix = "_upload"

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "<path:object_id>/change/upload/",
                self.admin_site.admin_view(self.upload_view),
                name=f'{self.model._meta.app_label}_{self.model._meta.model_name}{self.url_suffix}',
            )
        ]
        return my_urls + urls

    def upload_view(self, request, object_id, extra_context=None):
        model = self.model
        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, model._meta, object_id)

        context = dict(
            # Include common variables for rendering the admin template.
            self.admin_site.each_context(request),
            # Anything else you want in the context...
            csrf_token=request.META.get('CSRF_COOKIE'),
            asset_name=obj.name,
            collection_name=obj.get_collection(),
        )

        if hasattr(obj, 'item'):
            context['item_name'] = obj.item.name

        return TemplateResponse(request, self.upload_template_name, context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.model.objects.\
            filter(id=request.resolver_match.kwargs['object_id']).first()

        if getattr(obj, "is_external", False):  #check if the object is external
            return super().change_view(request, object_id, form_url)

        extra_context = extra_context or {}
        property_upload_url = reverse(
            f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}{self.url_suffix}',
            args=[object_id],
        )
        extra_context['property_upload_url'] = property_upload_url
        return super().change_view(request, object_id, form_url, extra_context=extra_context)


class RedirectAfterCreationMixin:

    def response_add(self, request, obj, post_url_continue=None):
        """
        After adding a new object, redirect to the change form for the new object
        unless the user clicked "Save and add another".
        """
        if "_addanother" not in request.POST:
            request.POST = request.POST.copy()
            request.POST["_continue"] = 1

        return super().response_add(request, obj, post_url_continue)


class CollectionAssetAdminForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.id is not None:
            if 'is_external' in self.fields:
                external_field = self.fields['is_external']
                external_field.help_text = (
                    _('Whether this asset is hosted externally. Save the form in '
                      'order to toggle the file field between input and file widget.')
                )


@admin.register(CollectionAsset)
class CollectionAssetAdmin(AssetUploadAdminMixin, RedirectAfterCreationMixin, admin.ModelAdmin):
    form = CollectionAssetAdminForm

    class Media:
        js = ('js/admin/asset_help_search.js',)
        css = {'all': ('style/hover.css',)}

    autocomplete_fields = ['collection']
    search_fields = ['name', 'collection__name']
    readonly_fields = [
        'file',
        'collection_name',
        'href',
        'is_external',
        'checksum_multihash',
        'created',
        'updated',
        'etag',
        'update_interval',
        'displayed_file_size',
    ]
    list_display = ['name', 'collection_name', 'collection_published']
    fieldsets = (
        (None, {
            'fields': ('name', 'collection', 'created', 'updated', 'etag')
        }),
        (
            'File',
            {
                'fields': (
                    'file',
                    'media_type',
                    'href',
                    'checksum_multihash',
                    'update_interval',
                    'displayed_file_size'
                )
            }
        ),
        ('Description', {
            'fields': ('title', 'description', 'roles')
        }),
        ('Attributes', {
            'fields': ['proj_epsg']
        }),
    )

    list_filter = [AutocompleteFilterFactory('Collection name', 'collection', use_pk_exact=True)]

    def get_readonly_fields(self, request, obj=None):
        # If the object is not None it means that is an update action
        if obj:
            # Don't allow to modify Asset name and media type, because they are tightly coupled
            # with the asset data file. Changing them require to re-upload the data.
            return self.readonly_fields + ['name', 'media_type']
        return self.readonly_fields

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term.startswith('"') and search_term.endswith('"'):
            search_terms = search_term.strip('"').split('/', maxsplit=2)
            if len(search_terms) == 2:
                collection_name = search_terms[0]
                asset_name = search_terms[1]
            else:
                collection_name = None
                asset_name = search_terms[0]
            queryset |= self.model.objects.filter(name__exact=asset_name)
            if collection_name:
                queryset &= self.model.objects.filter(collection__name__exact=collection_name)
        return queryset, use_distinct

    def collection_published(self, instance):
        return instance.collection.published

    collection_published.admin_order_field = 'collection__published'
    collection_published.short_description = 'Published'
    collection_published.boolean = True

    def collection_name(self, instance):
        return instance.collection.name

    collection_name.admin_order_field = 'collection__name'
    collection_name.short_description = 'Collection Id'

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
        if instance.is_external:
            url = instance.file.name
        else:
            url = build_asset_href(self.request, instance.file.name)
        return format_html("<a href='{url}'>{url}</a>", url=url)

    #helper function which displays the bytes in human-readable format
    def displayed_file_size(self, instance):
        return filesizeformat(instance.file_size)

    displayed_file_size.short_description = 'File size'

    # We don't want to move the assets on S3
    # That's why some fields like the name of the asset are set readonly here
    # for update operations
    def get_fieldsets(self, request, obj=None):
        """Build the different field sets for the admin page."""

        base_fields = super().get_fieldsets(request, obj)

        if obj is None:
            return [
                (None, {
                    'fields': ('name', 'collection', 'created', 'updated', 'etag')
                }),
                ('File', {
                    'fields': ('media_type',)
                }),
            ]

        # Define file fields conditionally based on `allow_external_assets`
        if obj.collection.allow_external_assets:
            file_fields = (
                'is_external',
                'file',
                'media_type',
                'href',
                'checksum_multihash',
                'update_interval',
                'displayed_file_size'
            )
        else:
            file_fields = (
                'file',
                'media_type',
                'href',
                'checksum_multihash',
                'update_interval',
                'displayed_file_size'
            )

        return [
            (None, {
                'fields': ('name', 'collection_name', 'created', 'updated', 'etag')
            }),
            ('File', {
                'fields': file_fields
            }),
            ('Description', {
                'fields': ('title', 'description', 'roles')
            }),
        ]


class AssetAdminForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        """If it's an external asset, we switch the file field to a char field"""
        super().__init__(*args, **kwargs)

        if self.instance is not None and self.instance.id is not None:
            are_external_assets_allowed = self.instance.item.collection.allow_external_assets

            if are_external_assets_allowed:

                external_field = self.fields['is_external']
                external_field.help_text = (
                    _('Whether this asset is hosted externally. Save the form in '
                      'order to toggle the file field between input and file widget.')
                )

                if self.instance.is_external:
                    # can't just change the widget, otherwise it is impossible to
                    # change the value!
                    self.fields['file'] = forms.CharField(
                        label='File',
                        required=False,
                        widget=forms.TextInput(attrs={'size': 150}),
                    )

                    self.fields['file'].widget.attrs['placeholder'
                                                    ] = 'https://map.geo.admin.ch/external.jpg'

    def clean_file(self):
        if self.instance:
            external_changed = 'is_external' in self.changed_data
            is_external = self.cleaned_data.get('is_external')

            # if we're just changing from internal to external, so we don't
            # validate the url, because it is potentially still the previous,
            # internal file
            if is_external and not external_changed:
                file = self.cleaned_data.get('file')

                validate_href_url(file, self.instance.item.collection)
                validate_href_reachability(file, self.instance.item.collection)

        return self.cleaned_data.get('file')


class NotUploadedYetFilter(SimpleListFilter):
    """Provide a filter for assets that helps with sorting out invalid items"""

    title = 'Not uploaded yet'
    parameter_name = 'file_size'

    def lookups(self, request, model_admin):
        return [
            ('0', _('Upload in progress')), ('none', _('Not found on s3'))
        ]

    def queryset(self, request, queryset):
        if self.value() == '0':
            return queryset.filter(file_size=0)
        if self.value() == 'none':
            return queryset.filter(file_size=None)
        return queryset


@admin.register(Asset)
class AssetAdmin(AssetUploadAdminMixin, RedirectAfterCreationMixin, admin.ModelAdmin):
    form = AssetAdminForm

    class Media:
        js = ('js/admin/asset_help_search.js', 'js/admin/asset_external_fields.js')
        css = {'all': ('style/hover.css',)}

    file = forms.FileField(required=False)

    autocomplete_fields = ['item']
    search_fields = ['name', 'item__name', 'item__collection__name']

    # We don't want to move the assets on S3
    # That's why some fields like the name of the asset are set readonly here
    # for update operations
    readonly_fields = [
        'item_name',
        'collection_name',
        'href',
        'checksum_multihash',
        'created',
        'updated',
        'etag',
        'update_interval',
        'displayed_file_size',
    ]

    list_display = [
        'name', 'item_name', 'collection_name', 'collection_published', 'created', 'updated'
    ]

    list_filter = [
        AutocompleteFilterFactory('Item name', 'item', use_pk_exact=True),
        AutocompleteFilterFactory('Collection name', 'item__collection', use_pk_exact=True),
        NotUploadedYetFilter
    ]

    def get_readonly_fields(self, request, obj=None):
        # If the object is not None it means that is an update action
        if obj:
            # Don't allow to modify Asset name and media type, because they are tightly coupled
            # with the asset data file. Changing them require to re-upload the data.
            # As file upload through admin has been disabled,
            # the field is read-only unless the asset is external.
            if not obj.is_external:
                return self.readonly_fields + ['file', 'name', 'media_type']

            return self.readonly_fields + ['name', 'media_type']
        return self.readonly_fields

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

    def href(self, instance):
        if instance.is_external:
            url = instance.file.name
        else:
            url = build_asset_href(self.request, instance.file.name)
        return format_html("<a href='{url}'>{url}</a>", url=url)

    #helper function which displays the bytes in human-readable format
    def displayed_file_size(self, instance):
        return filesizeformat(instance.file_size)

    displayed_file_size.short_description = 'File size'

    def get_fieldsets(self, request, obj=None):
        """Build the different field sets for the admin page

        The create page takes less fields than the edit page. This is because
        at creation time we don't know yet if the collection allows for external
        assets and thus can't determine whether to show the flag or not
        """

        # Save the request for use in the href field
        self.request = request  # pylint: disable=attribute-defined-outside-init

        fields = []
        if obj is None:
            fields.append((None, {'fields': ('name', 'item', 'created', 'updated', 'etag')}))
            fields.append(('File', {'fields': ('media_type',)}))
        else:
            # add one section after another
            fields.append((
                None, {
                    'fields':
                        ('name', 'item_name', 'collection_name', 'created', 'updated', 'etag')
                }
            ))

            # is_external is only available if the collection allows it
            if obj.item.collection.allow_external_assets:
                file_fields = (
                    'is_external',
                    'file',
                    'media_type',
                    'href',
                    'checksum_multihash',
                    'update_interval',
                    'displayed_file_size'
                )
            else:
                file_fields = (
                    'file',
                    'media_type',
                    'href',
                    'checksum_multihash',
                    'update_interval',
                    'displayed_file_size'
                )

            fields.append(('File', {'fields': file_fields}))

            fields.append(('Description', {'fields': ('title', 'description', 'roles')}))

            fields.append((
                'Attributes', {
                    'fields': ('eo_gsd', 'proj_epsg', 'geoadmin_variant', 'geoadmin_lang')
                }
            ))

        return fields

    def get_form(self, request, obj=None, change=False, **kwargs):
        """Make the file field optional

        It is perfectly possible to not specify any file in the file field when saving,
        even when the field *isn't* blank=True or null=True. The multipart-upload
        process does it too.
        We allow the field to be empty in case somebody is setting the is_external flag"""
        form = super().get_form(request, obj, change, **kwargs)
        return form


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
        'checksum_multihash',
        'update_interval',
        'content_encoding'
    ]
    list_display = [
        'short_upload_id', 'status', 'asset_name', 'item_name', 'collection_name', 'created'
    ]
    fieldsets = (
        (None, {
            'fields': ('upload_id', 'asset_name', 'item_name', 'collection_name', 'status')
        }),
        (
            'Attributes',
            {
                'fields': (
                    'number_parts',
                    'urls_json',
                    'checksum_multihash',
                    'created',
                    'ended',
                    'update_interval',
                    'content_encoding'
                )
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
