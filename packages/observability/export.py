"""Choosing where spans go, and guaranteeing they leave before the process does.

Selection is resolved once, in a process entry point, from the environment. The
instrumented code never learns which backend it reached — that is the whole
reason the instrumentation is OpenTelemetry rather than a Cloud Trace client.

Two properties matter more than throughput here. A remediation is a handful of
spans, but the process carrying them is often a Cloud Run job or a pull-based
worker that exits as soon as the run finishes, so an unflushed batch is a lost
trace. And a trace backend that is unreachable must not be able to fail a run:
every path in this module degrades to a working provider rather than raising.
"""

from __future__ import annotations

import atexit
import logging
import os
from typing import Any, Final, TextIO

from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanProcessor,
)

from packages.observability.config import (
    ATTR_GCP_PROJECT,
    ENV_TRACE_EXPORTER,
    EXPORTER_AUTO,
    EXPORTER_CLOUD,
    EXPORTER_CONSOLE,
    EXPORTER_NONE,
    PROJECT_VARS,
    TELEMETRY_ENDPOINT,
    TRACE_FLUSH_TIMEOUT_MS,
    TRACING_SCHEMA_VERSION,
)

log = logging.getLogger(__name__)

_VALID_MODES: Final[frozenset[str]] = frozenset(
    {EXPORTER_AUTO, EXPORTER_CLOUD, EXPORTER_CONSOLE, EXPORTER_NONE}
)

_CREDENTIAL_SCOPES: Final[tuple[str, ...]] = ("https://www.googleapis.com/auth/cloud-platform",)


def configured_mode(env: dict[str, str] | None = None) -> str:
    """The requested exporter mode, defaulting to `auto`.

    An unrecognised value resolves to `auto` rather than failing: a typo in a
    deployment variable should cost the operator a warning, not the service.
    """
    environ = env if env is not None else dict(os.environ)
    mode = environ.get(ENV_TRACE_EXPORTER, "").strip().lower() or EXPORTER_AUTO
    if mode not in _VALID_MODES:
        log.warning("unknown %s=%r; using %r", ENV_TRACE_EXPORTER, mode, EXPORTER_AUTO)
        return EXPORTER_AUTO
    return mode


def cloud_project(env: dict[str, str] | None = None) -> str:
    """The project spans are routed to, from either accepted variable."""
    environ = env if env is not None else dict(os.environ)
    for name in PROJECT_VARS:
        value = environ.get(name, "").strip()
        if value:
            return value
    return ""


def cloud_trace_unavailable_reason(env: dict[str, str] | None = None) -> str | None:
    """Return `None` when spans can reach Cloud Trace, else why they cannot."""
    if not cloud_project(env):
        return f"none of {', '.join(PROJECT_VARS)} is set"
    try:
        import grpc  # noqa: F401
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # noqa: F401
            OTLPSpanExporter,
        )
    except ImportError as exc:
        return f"opentelemetry-exporter-otlp-proto-grpc is not installed ({exc})"
    return None


def _gcp_resource() -> Resource | None:
    """Cloud Run service, revision, and region, when running on Google Cloud.

    Without this a span from the worker pool and a span from the agent service
    are indistinguishable in Cloud Trace, which defeats asking the obvious
    question of which lane a run executed in.
    """
    try:
        from opentelemetry.resourcedetector.gcp_resource_detector import (
            GoogleCloudResourceDetector,
        )

        return GoogleCloudResourceDetector(raise_on_error=False).detect()
    except Exception as exc:
        log.debug("no Google Cloud resource attributes: %s", exc)
        return None


def build_resource(service_name: str, env: dict[str, str] | None = None) -> Resource:
    """Identify this process to the trace backend.

    `gcp.project_id` is set explicitly rather than left to detection: on Cloud Run
    the detector supplies it, but a local run against a real project has no
    metadata server, and the Telemetry API rejects a span that cannot be routed.
    """
    attributes: dict[str, Any] = {
        SERVICE_NAME: service_name,
        SERVICE_VERSION: TRACING_SCHEMA_VERSION,
    }
    project = cloud_project(env)
    if project:
        attributes[ATTR_GCP_PROJECT] = project
    resource = Resource.create(attributes)
    detected = _gcp_resource()
    return resource.merge(detected) if detected is not None else resource


def build_processor(
    *,
    mode: str,
    out: TextIO | None = None,
    env: dict[str, str] | None = None,
) -> SpanProcessor | None:
    """The span processor for `mode`, or `None` when tracing is off.

    `SimpleSpanProcessor` for the console so a crashed run still leaves the trace
    that explains why, and `BatchSpanProcessor` for Cloud Trace because each
    export is a network round trip that must not sit on the run's critical path.
    """
    if mode == EXPORTER_NONE:
        return None
    if mode in {EXPORTER_AUTO, EXPORTER_CLOUD}:
        reason = cloud_trace_unavailable_reason(env)
        if reason is None:
            return BatchSpanProcessor(_cloud_exporter(env))
        if mode == EXPORTER_CLOUD:
            # Asked for explicitly, so silence would hide a misconfigured
            # deployment that looks instrumented and exports nothing.
            log.warning("Cloud Trace requested but unavailable: %s", reason)
        else:
            log.info("tracing to the console: %s", reason)
    return SimpleSpanProcessor(ConsoleSpanExporter(out=out))


def _cloud_exporter(env: dict[str, str] | None = None) -> Any:
    """OTLP over gRPC to the Telemetry API, authenticated as this workload.

    Application Default Credentials are attached per call rather than per channel
    so a worker that outlives its access token keeps exporting.
    """
    import google.auth
    import google.auth.transport.requests
    import grpc
    from google.auth.transport.grpc import AuthMetadataPlugin
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    # Scoped explicitly: a service-account credential resolved without scopes
    # cannot mint a token, and the failure surfaces as an unauthenticated gRPC
    # channel rather than anything that names the cause.
    credentials, _ = google.auth.default(scopes=list(_CREDENTIAL_SCOPES))
    auth_plugin = AuthMetadataPlugin(
        credentials=credentials, request=google.auth.transport.requests.Request()
    )
    channel_credentials = grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(),
        grpc.metadata_call_credentials(auth_plugin),
    )
    return OTLPSpanExporter(endpoint=TELEMETRY_ENDPOINT, credentials=channel_credentials)


def install_process_tracing(
    service_name: str,
    *,
    out: TextIO | None = None,
    env: dict[str, str] | None = None,
) -> TracerProvider:
    """Install the global tracer provider for one process, and flush it on exit.

    Call this from an entry point exactly once. OpenTelemetry ignores a second
    global provider, so a library that called this would silently win or lose
    depending on import order.
    """
    from opentelemetry import trace

    provider = TracerProvider(resource=build_resource(service_name, env))
    processor = build_processor(mode=configured_mode(env), out=out, env=env)
    if processor is not None:
        provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    atexit.register(flush_tracing, provider)
    return provider


def flush_tracing(provider: TracerProvider, timeout_millis: int = TRACE_FLUSH_TIMEOUT_MS) -> None:
    """Export whatever is still buffered. Safe to call more than once.

    A failure here is logged and swallowed. This runs while a process is already
    on its way out, and losing a trace is not worth turning a completed run into
    a crashed one.
    """
    try:
        provider.force_flush(timeout_millis)
    except Exception as exc:
        log.warning("could not flush spans: %s", exc)


__all__ = [
    "build_processor",
    "build_resource",
    "cloud_trace_unavailable_reason",
    "configured_mode",
    "flush_tracing",
    "install_process_tracing",
]
