"""Pinned span and attribute names.

A trace is evidence in this product: the demo shows the agent topology from it,
and an audit answers "what did the run actually do" from it. Names therefore
live here rather than at call sites, so renaming one is a single visible change
and a dashboard query cannot quietly stop matching.
"""

from typing import Final

TRACING_SCHEMA_VERSION: Final[str] = "1.0.0"

DEFAULT_SERVICE_NAME: Final[str] = "patchapi"

# Where spans go. `auto` resolves to Cloud Trace when a project is configured and
# the exporter is installed, and to the console otherwise, so the same image
# traces to Agent Observability in Cloud Run and to stdout on a laptop without a
# per-environment code path.
ENV_TRACE_EXPORTER: Final[str] = "PATCHAPI_TRACE_EXPORTER"
EXPORTER_AUTO: Final[str] = "auto"
EXPORTER_CLOUD: Final[str] = "cloud"
EXPORTER_CONSOLE: Final[str] = "console"
EXPORTER_NONE: Final[str] = "none"

# Both names, in this order, matching `packages/state/provider_check.py`. The
# deployment sets `GCP_PROJECT`; the Google SDKs read `GOOGLE_CLOUD_PROJECT`.
# Accepting one only would have traced to the console in production while
# reporting itself as configured.
PROJECT_VARS: Final[tuple[str, ...]] = ("GCP_PROJECT", "GOOGLE_CLOUD_PROJECT")

# Cloud Trace ingests OTLP natively through the Telemetry API, and the older
# `CloudTraceSpanExporter` is deprecated. Exporting OTLP also means the spans are
# not reshaped on the way out: semantic-convention keys survive verbatim, which
# is what makes the same trace readable outside Google Cloud.
TELEMETRY_ENDPOINT: Final[str] = "telemetry.googleapis.com"

# The Telemetry API routes on this resource attribute, so a span without it is
# rejected as INVALID_ARGUMENT rather than stored somewhere unexpected.
ATTR_GCP_PROJECT: Final[str] = "gcp.project_id"

# A remediation runs as a Cloud Run job or a pull-based worker, so the process
# can exit while the batch processor still holds spans. Entry points flush on the
# way out; this bounds how long shutdown waits for that.
TRACE_FLUSH_TIMEOUT_MS: Final[int] = 10_000

# The parent the stage spans hang from. Without one, a single remediation
# arrives at the backend as seven unrelated traces, which is not a chain anyone
# can read.
SPAN_RUN: Final[str] = "patchapi.run"

# One span per pipeline stage (roadmap §8), named so a trace reads as the run.
SPAN_CHANGE_INTELLIGENCE: Final[str] = "patchapi.change_intelligence"
SPAN_IMPACT: Final[str] = "patchapi.impact"
SPAN_POLICY: Final[str] = "patchapi.policy"
SPAN_PATCH: Final[str] = "patchapi.patch"
SPAN_SANDBOX: Final[str] = "patchapi.sandbox"
SPAN_VERIFICATION: Final[str] = "patchapi.verification"
SPAN_PULL_REQUEST: Final[str] = "patchapi.pull_request"

# Attribute keys. Prefixed to avoid colliding with OpenTelemetry semantic
# conventions, which own the unprefixed namespace.
ATTR_RUN_ID: Final[str] = "patchapi.run_id"
ATTR_CHANGE_ID: Final[str] = "patchapi.change_id"
ATTR_REPO: Final[str] = "patchapi.repo"
ATTR_BASE_SHA: Final[str] = "patchapi.base_sha"
ATTR_POLICY_OUTCOME: Final[str] = "patchapi.policy_outcome"
ATTR_TRUST: Final[str] = "patchapi.trust"
ATTR_MODEL_ID: Final[str] = "patchapi.model_id"
ATTR_ATTEMPT: Final[str] = "patchapi.attempt"

# Span events, not attributes: each marks a moment inside a stage rather than
# describing it, and each carries a name only. Whether institutional context was
# available is a fact about the run worth reading off a trace; the sentence
# explaining why it was not has spaces in it, so it goes to the log instead.
EVENT_MEMORY_RECALLED: Final[str] = "patchapi.memory.recalled"
EVENT_MEMORY_UNAVAILABLE: Final[str] = "patchapi.memory.unavailable"
EVENT_MEMORY_RECORDED: Final[str] = "patchapi.memory.recorded"
EVENT_MEMORY_NOT_RECORDED: Final[str] = "patchapi.memory.not_recorded"
