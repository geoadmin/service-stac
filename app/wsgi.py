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

import gevent.queue
import gevent.util

if os.environ.get('GEVENT_PATCH_URLLIB3_CPOOL_QUEUE', True):
    # Work around gevent deadlock https://github.com/gevent/gevent/issues/1957
    # As seen in PB-1531.
    import urllib3.connectionpool
    urllib3.connectionpool.ConnectionPool.QueueCls = gevent.queue.LifoQueue

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
            key: value for key,
            value in self.options.items() if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


class GeventWorkerWithStackDump(GeventWorker):
    # We want to dump the stacks when the worker receives SIGTERM regardless
    # of whether it handles the SIGTERM gracefully. If the worker remains stuck,
    # the next signal the master sends is SIGKILL, which means the worker_exit
    # handler is never called. Thus, we spawn a thread to dump the stack
    # before actually attempting to handle the signal.
    def handle_exit(self, sig, frame):
        gevent.spawn(self.dump_stacks)
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
        'worker_class': 'gevent',
        'workers': int(os.environ.get('GUNICORN_WORKERS',
                                      '2')),  # scaling horizontally is left to Kubernetes
        'worker_tmp_dir': os.environ.get('GUNICORN_WORKER_TMP_DIR', None),
        'timeout': 60,
        'logconfig_dict': get_logging_config(),
    }
    if os.environ.get('GUNICORN_DUMP_STACKS_ON_EXIT', False):
        options['worker_class'] = 'wsgi.GeventWorkerWithStackDump'
    StandaloneApplication(application, options).run()
