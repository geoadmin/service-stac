# pylint: disable=ungrouped-imports
from os import environ
from os import getenv

from helpers.strtobool import strtobool

from django.core.asgi import get_asgi_application

environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()

if not strtobool(getenv("OTEL_SDK_DISABLED", "false")):
    from helpers.otel import initialize_tracing
    from helpers.otel import setup_trace_provider
    from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

    setup_trace_provider()
    initialize_tracing()

    application = OpenTelemetryMiddleware(application)
