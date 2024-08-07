from django.contrib import admin
from django.utils.translation import gettext_lazy as _


class StacAdminSite(admin.AdminSite):
    site_header = _('STAC API admin')
    site_title = _('geoadmin STAC API')
    # This is normally used to redirect URLs that are missing a trailing slash.
    # We have our own special redirection code in middleware.internal_redirect
    # for this and it doesn't play well with this feature. So we disable it.
    final_catch_all_view = False
