"""OpenTelemetry tracer setup (roadmap §14).

Instrumentation is standards-based so the same spans reach Agent Observability
and Cloud Trace in Google Cloud, and a console exporter locally, without the
instrumented code knowing which. `configure_tracing` returns a provider rather
than installing one globally by default: a test needs its own isolated provider,
and a library that mutates global state on import is unusable inside a sandbox
runner that also traces.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, TextIO

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode

from packages.observability.config import (
    DEFAULT_SERVICE_NAME,
    TRACING_SCHEMA_VERSION,
)


def configure_tracing(
    *,
    service_name: str = DEFAULT_SERVICE_NAME,
    out: TextIO | None = None,
    install_globally: bool = False,
) -> TracerProvider:
    """Build a tracer provider that exports spans as JSON lines.

    `SimpleSpanProcessor` rather than the batching one: spans are exported as
    they end, so a run that crashes still leaves the trace that explains why.
    Throughput is not the constraint here — a run is a handful of spans.

    Set `install_globally` only in a process entry point. OpenTelemetry ignores
    a second global provider, so installing one from a library would silently
    win or silently lose depending on import order.
    """
    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: TRACING_SCHEMA_VERSION,
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter(out=out)))
    if install_globally:
        trace.set_tracer_provider(provider)
    return provider


def get_tracer(
    name: str = DEFAULT_SERVICE_NAME, provider: TracerProvider | None = None
) -> trace.Tracer:
    """Return a tracer from `provider`, or from the installed global one."""
    if provider is not None:
        return provider.get_tracer(name)
    return trace.get_tracer(name)


@contextmanager
def span(
    name: str,
    *,
    attributes: Mapping[str, Any] | None = None,
    provider: TracerProvider | None = None,
) -> Iterator[Span]:
    """Record one stage of a run.

    An exception is recorded on the span and re-raised: a failed stage has to
    appear in the trace, because "the trace shows what the run did" is only
    true if the failures are in it too.
    """
    tracer = get_tracer(provider=provider)
    with tracer.start_as_current_span(name) as active_span:
        if attributes:
            for key, value in attributes.items():
                active_span.set_attribute(key, value)
        try:
            yield active_span
        except Exception as exc:
            active_span.record_exception(exc)
            active_span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
