#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""

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
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
