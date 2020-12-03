from django.contrib import admin
from django.utils.translation import gettext_lazy as _


class StacAdminSite(admin.AdminSite):
    site_header = _('STAC API admin')
    site_title = _('geoadmin STAC API')
