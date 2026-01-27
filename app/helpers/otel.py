from os import getenv

from helpers.strtobool import strtobool

# Opentelemetry tends to do a bit too much magic, we therefore only import the packages if we
# really need them.
# pylint: disable=import-outside-toplevel


def initialize_tracing():
    if not strtobool(getenv("OTEL_SDK_DISABLED", "false")):
        if strtobool(getenv("OTEL_ENABLE_DJANGO", "false")):
            from opentelemetry.instrumentation.django import DjangoInstrumentor
            DjangoInstrumentor().instrument()
        if strtobool(getenv("OTEL_ENABLE_BOTO", "false")):
            from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
            BotocoreInstrumentor().instrument()
        if strtobool(getenv("OTEL_ENABLE_PSYCOPG", "false")):
            from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
            PsycopgInstrumentor().instrument()
        if strtobool(getenv("OTEL_ENABLE_LOGGING", "false")):
            from opentelemetry.instrumentation.logging import LoggingInstrumentor
            LoggingInstrumentor().instrument()


def setup_trace_provider():
    if not strtobool(getenv("OTEL_SDK_DISABLED", "false")):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.trace import set_tracer_provider

        # Since we created a new tracer, the default span processor is gone. We need to
        # create a new one using the default OTEL env variables and ad it to the tracer.
        span_processor = BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=getenv('OTEL_EXPORTER_OTLP_ENDPOINT', "http://localhost:4317"),
                headers=getenv('OTEL_EXPORTER_OTLP_HEADERS'),
                insecure=strtobool(getenv('OTEL_EXPORTER_OTLP_INSECURE', "false"))
            )
        )

        provider = TracerProvider(resource=Resource.create())
        provider.add_span_processor(span_processor)
        set_tracer_provider(provider)
