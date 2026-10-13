"""
Wires up the OpenTelemetry SDK: a TracerProvider, a Resource describing this
service, and an OTLP exporter pointed at the Collector (Terminal 2 / Docker
Compose). Every other module just calls trace.get_tracer(__name__) - this
file is the ONLY place that configures where spans go.

Swap OTEL_EXPORTER in .env to "console" to print spans to stdout with no
Collector running at all - useful for a first look before standing up the
full Collector -> Jaeger pipeline.
"""
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased

_initialized = False


def init_tracing():
    global _initialized
    if _initialized:
        return trace.get_tracer_provider()

    sample_ratio = float(os.environ.get("OTEL_TRACE_SAMPLE_RATIO", "1.0"))
    resource = Resource.create({
        SERVICE_NAME: "nidan-lloyds-agent",
        SERVICE_VERSION: "0.1.0",
        "deployment.environment": os.environ.get("DEPLOY_ENV", "lab"),
    })

    # ParentBased + TraceIdRatioBased: a sampling decision made once per trace
    # (at the root span) and inherited by every child span in that trace -
    # you never want half a trace sampled and half dropped.
    sampler = ParentBased(TraceIdRatioBased(sample_ratio))

    provider = TracerProvider(resource=resource, sampler=sampler)

    exporter_kind = os.environ.get("OTEL_EXPORTER", "otlp").lower()
    if exporter_kind == "console":
        exporter = ConsoleSpanExporter()
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _initialized = True
    return provider


def get_tracer(name: str = "drishti"):
    init_tracing()
    return trace.get_tracer(name)
