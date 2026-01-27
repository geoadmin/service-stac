import os

from config.settings import get_logging_config

# pylint: disable=invalid-name
bind = f"0.0.0.0:{os.environ.get('HTTP_PORT', '8000')}"
worker_class = "uvicorn_worker.UvicornWorker"
worker_tmp_dir = os.environ.get('GUNICORN_WORKER_TMP_DIR', None)
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "2"))
logconfig_dict = get_logging_config()
