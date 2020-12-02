from django.contrib.admin.apps import AdminConfig


class StacAdminConfig(AdminConfig):
    default_site = 'config.admin.StacAdminSite'
