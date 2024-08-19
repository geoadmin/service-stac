import environ

env = environ.Env()


def check_toolbar_env(request):
    """ callback to check whether debug toolbar should be shown or not

    for details see
    https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config  # pylint: disable=line-too-long
    """

    return env.bool('DEBUG', False)
