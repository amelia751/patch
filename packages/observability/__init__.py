"""OpenTelemetry instrumentation helpers (roadmap §14).

Spans are the run's visible trace: the dashboard renders the agent topology
from them and an auditor answers "what did this run do" from them.
"""

from packages.observability.config import (
    ATTR_ATTEMPT,
    ATTR_BASE_SHA,
    ATTR_CHANGE_ID,
    ATTR_MODEL_ID,
    ATTR_POLICY_OUTCOME,
    ATTR_REPO,
    ATTR_RUN_ID,
    ATTR_TRUST,
    DEFAULT_SERVICE_NAME,
    EVENT_MEMORY_NOT_RECORDED,
    EVENT_MEMORY_RECALLED,
    EVENT_MEMORY_RECORDED,
    EVENT_MEMORY_UNAVAILABLE,
    SPAN_CHANGE_INTELLIGENCE,
    SPAN_IMPACT,
    SPAN_PATCH,
    SPAN_POLICY,
    SPAN_PULL_REQUEST,
    SPAN_RUN,
    SPAN_SANDBOX,
    SPAN_VERIFICATION,
    TRACING_SCHEMA_VERSION,
)
from packages.observability.export import (
    cloud_trace_unavailable_reason,
    configured_mode,
    flush_tracing,
    install_process_tracing,
)
from packages.observability.tracing import configure_tracing, get_tracer, span

__all__ = [
    "ATTR_ATTEMPT",
    "ATTR_BASE_SHA",
    "ATTR_CHANGE_ID",
    "ATTR_MODEL_ID",
    "ATTR_POLICY_OUTCOME",
    "ATTR_REPO",
    "ATTR_RUN_ID",
    "ATTR_TRUST",
    "DEFAULT_SERVICE_NAME",
    "EVENT_MEMORY_NOT_RECORDED",
    "EVENT_MEMORY_RECALLED",
    "EVENT_MEMORY_RECORDED",
    "EVENT_MEMORY_UNAVAILABLE",
    "SPAN_CHANGE_INTELLIGENCE",
    "SPAN_IMPACT",
    "SPAN_PATCH",
    "SPAN_POLICY",
    "SPAN_PULL_REQUEST",
    "SPAN_RUN",
    "SPAN_SANDBOX",
    "SPAN_VERIFICATION",
    "TRACING_SCHEMA_VERSION",
    "cloud_trace_unavailable_reason",
    "configure_tracing",
    "configured_mode",
    "flush_tracing",
    "get_tracer",
    "install_process_tracing",
    "span",
]
