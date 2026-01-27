from os import environ

from config.settings import get_logging_config
from gunicorn.app.base import BaseApplication
from helpers.otel import initialize_tracing
from helpers.otel import setup_trace_provider

from django.core.asgi import get_asgi_application

environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()

setup_trace_provider()
application = initialize_tracing(asgi_application=application)


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


if __name__ == '__main__':
    HTTP_PORT = str(environ.get('HTTP_PORT', "8000"))
    # Bind to 0.0.0.0 to let your app listen to all network interfaces.
    options = {
        'bind': f"{'0.0.0.0'}:{HTTP_PORT}",
        'worker_class': 'uvicorn_worker.UvicornWorker',
        'workers': int(environ.get('GUNICORN_WORKERS',
                                   '2')),  # scaling horizontally is left to Kubernetes
        'worker_tmp_dir': environ.get('GUNICORN_WORKER_TMP_DIR', None),
        'timeout': 60,
        'graceful_timeout': int(environ.get('GUNICORN_GRACEFUL_TIMEOUT', 30)),
        'keepalive': int(environ.get('GUNICORN_KEEPALIVE', 2)),
        'logconfig_dict': get_logging_config(),
    }
    StandaloneApplication(application, options).run()
