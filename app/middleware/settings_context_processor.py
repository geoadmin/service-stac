from django.conf import settings


def inject_settings_values(request):
    """
    Context processor to inject specific settings values into
    the template rendering context. Values should be prefixed
    with 'SETTINGS_' and otherwise use the same name as in the
    settings file.
    """
    return {'SETTINGS_APP_VERSION': settings.APP_VERSION}
