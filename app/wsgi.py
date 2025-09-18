#!/usr/bin/env python
"""
The gevent monkey import and patch suppress a warning, and a potential problem.
Gunicorn would call it anyway, but if it tries to call it after the ssl module
has been initialized in another module (like, in our code, by the botocore library),
then it could lead to inconsistencies in how the ssl module is used. Thus we patch
the ssl module through gevent.monkey.patch_all before any other import, especially
the app import, which would cause the boto module to be loaded, which would in turn
load the ssl module.

NOTE: We do this only if wsgi.py is the main program, when running django runserver
for local development, monkey patching creates the following error:

    `RuntimeError: cannot release un-acquired lock`

isort:skip_file
"""
# pylint: disable=wrong-import-position
if __name__ == '__main__':
    import gevent.monkey
    gevent.monkey.patch_all()
"""
WSGI config for project project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/howto/deployment/wsgi/
"""
import logging
import os

import gevent.util

from gunicorn.app.base import BaseApplication
from gunicorn.workers.ggevent import GeventWorker

from django.core.wsgi import get_wsgi_application

# Here we cannot uses `from django.conf import settings` because it breaks the `make gunicornserver`
from config.settings import get_logging_config

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
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


class GeventWorkerWithStackDump(GeventWorker):
    # We want to dump the stacks when the worker fails to exit gracefully.
    # The definition of gunicorn graceful termination is to send a SIGTERM,
    # wait graceful_timeout then send a SIGKILL. So, upon receiving the SIGTERM,
    # we schedule a thread that waits a little less than graceful_timeout then
    # dump the stacks. If the process exited before then, no stack dumping
    # occurs and we don't clutter the logs unnecessarily.
    # A nicer way to resolve this has been proposed to upstream in
    # https://github.com/benoitc/gunicorn/issues/3385

    def get_stack_dump_delay(self):
        delay = float(os.environ.get('GUNICORN_STACK_DUMP_DELAY', self.cfg.graceful_timeout - 1))
        return max(0, delay)

    def handle_exit(self, sig, frame):
        gevent.spawn_later(self.get_stack_dump_delay(), self.dump_stacks)
        super().handle_exit(sig, frame)

    @staticmethod
    def dump_stacks():
        logger = logging.getLogger(__name__)
        logger.error('Dumping gevent stacks:\n%s', '\n'.join(gevent.util.format_run_info()))


# We use the port 5000 as default, otherwise we set the HTTP_PORT env variable within the container.
if __name__ == '__main__':
    HTTP_PORT = str(os.environ.get('HTTP_PORT', "8000"))
    # Bind to 0.0.0.0 to let your app listen to all network interfaces.
    options = {
        'bind': f"{'0.0.0.0'}:{HTTP_PORT}",
        'worker_class': 'wsgi.GeventWorkerWithStackDump',
        'workers': int(os.environ.get('GUNICORN_WORKERS',
                                      '2')),  # scaling horizontally is left to Kubernetes
        'worker_tmp_dir': os.environ.get('GUNICORN_WORKER_TMP_DIR', None),
        'timeout': 60,
        'graceful_timeout': int(os.environ.get('GUNICORN_GRACEFUL_TIMEOUT', 30)),
        'keepalive': int(os.environ.get('GUNICORN_KEEPALIVE', 2)),
        'logconfig_dict': get_logging_config(),
    }
    StandaloneApplication(application, options).run()
