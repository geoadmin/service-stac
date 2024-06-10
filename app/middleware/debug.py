import os

from helpers.utils import strtobool


def check_toolbar_env(request):
    """ callback to check whether debug toolbar should be shown or not

    for details see
    https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config  # pylint: disable=line-too-long
    """

    return strtobool(os.environ.get('DEBUG', '0'))
