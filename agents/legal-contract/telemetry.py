import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

_initialized = False


def init_tracer(service_name: str, app=None):
    """Initialise OpenTelemetry → Cloud Trace exporter.

    Mirrors the pattern from agents/hr-leave/telemetry.py so that all
    legal-contract spans appear in the same Cloud Trace project alongside
    the other AgentMesh agents.
    """
    global _initialized
    if _initialized:
        return trace.get_tracer(service_name)

    project_id = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
    provider = TracerProvider()
    try:
        cloud_exporter = CloudTraceSpanExporter(project_id=project_id)
        provider.add_span_processor(BatchSpanProcessor(cloud_exporter))
    except Exception as e:
        print(
            f"[Telemetry] Warning: Could not initialize CloudTraceSpanExporter ({e}). "
            "Trace fallback active."
        )

    trace.set_tracer_provider(provider)

    if app is not None:
        try:
            FastAPIInstrumentor.instrument_app(app)
        except Exception as e:
            print(f"[Telemetry] Warning: Could not instrument FastAPI app: {e}")

    try:
        RequestsInstrumentor().instrument()
    except Exception as e:
        print(f"[Telemetry] Warning: Could not instrument Requests: {e}")

    _initialized = True
    return trace.get_tracer(service_name)
