#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from helpers.logging import redirect_std_to_logger
from helpers.otel import initialize_tracing
from helpers.otel import setup_trace_provider
from helpers.strtobool import strtobool
from opentelemetry import trace


def main():
    """Run administrative tasks."""

    # if we have .env.local file we are very likely on a development machine, therefore load it
    # to have the correct environment when using manage.py commands.
    env_file = '.env.local'
    if Path(env_file).is_file():
        print(f'WARNING: Load {env_file} environment')
        load_dotenv(env_file, override=True, verbose=True)

    # use separate settings.py for tests
    if 'test' in sys.argv:
        os.environ.setdefault('LOGGING_CFG', 'app/config/logging-cfg-unittest.yml')
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
    elif 'runserver' not in sys.argv:
        # uses another logging configuration for management command (except for runserver)
        os.environ.setdefault('LOGGING_CFG', 'app/config/logging-cfg-management.yml')
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    else:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

    try:
        from django.core.management import \
            execute_from_command_line  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    if not strtobool(os.getenv("OTEL_SDK_DISABLED", "false")):
        setup_trace_provider()
        initialize_tracing()
        name = sys.argv[1] if len(sys.argv) > 1 else sys.argv[0]
        tracer = trace.get_tracer(name)
        with tracer.start_as_current_span(name=name):
            execute_from_command_line(sys.argv)
    else:
        execute_from_command_line(sys.argv)


if __name__ == '__main__':
    if '--redirect-std-to-logger' in sys.argv:
        sys.argv.remove('--redirect-std-to-logger')
        with redirect_std_to_logger(__name__):
            main()
    else:
        main()
