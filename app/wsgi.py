#!/usr/bin/env python
"""
WSGI config for project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/howto/deployment/wsgi/
"""

# isort:skip_file
# pylint: disable=wrong-import-position,wrong-import-order,ungrouped-imports

# default to the setting that's being created in DOCKERFILE
from os import environ

environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Initialize OTEL.
# Initialize should be called as early as possible, but at least before the app is imported
# The order has a impact on how the libraries are instrumented. If called after app import,
# e.g. the django instrumentation has no effect.
from helpers.otel import initialize_tracing, setup_trace_provider

setup_trace_provider()
initialize_tracing()

import os

from gunicorn.app.base import BaseApplication

from django.core.wsgi import get_wsgi_application

# Here we cannot uses `from django.conf import settings` because it breaks the `make gunicornserver`
from config.settings import get_logging_config

application = get_wsgi_application()


class StandaloneApplication(BaseApplication):  # pylint: disable=abstract-method

    def __init__(self, app, options=None):  # pylint: disable=redefined-outer-name
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


# We use the port 5000 as default, otherwise we set the HTTP_PORT env variable within the container.
if __name__ == '__main__':
    HTTP_PORT = str(os.environ.get('HTTP_PORT', "8000"))
    # Bind to 0.0.0.0 to let your app listen to all network interfaces.
    options = {
        'bind': f"{'0.0.0.0'}:{HTTP_PORT}",
        'worker_class': 'gthread',
        'workers': int(os.environ.get('GUNICORN_WORKERS', '2')),
        'threads': int(os.environ.get('GUNICORN_THREADS', '4')),
        'worker_tmp_dir': os.environ.get('GUNICORN_WORKER_TMP_DIR', None),
        'timeout': 60,
        'graceful_timeout': int(os.environ.get('GUNICORN_GRACEFUL_TIMEOUT', 30)),
        'keepalive': int(os.environ.get('GUNICORN_KEEPALIVE', 2)),
        'logconfig_dict': get_logging_config(),
    }
    StandaloneApplication(application, options).run()
