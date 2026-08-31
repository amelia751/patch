# `packages/observability`

OpenTelemetry setup for PatchAPI agents and services.

Instrumentation is standards-based, so the same spans reach Agent Observability
and Cloud Trace in Google Cloud and a console exporter locally, without the
instrumented code knowing which. Span, attribute, and event names are pinned in
`config.py` so a rename is one visible change and a dashboard query cannot
quietly stop matching.

## Installing tracing in a process

```python
from packages.observability import install_process_tracing

provider = install_process_tracing("patchapi-remediation-worker")
```

Call this from an entry point exactly once. It installs the global tracer
provider and registers a flush on exit; OpenTelemetry ignores a second global
provider, so a library that called it would silently win or lose depending on
import order.

`configure_tracing` is not a substitute for it. That function is deliberately
console-only and independent of the environment, so a test can read the output
of a provider it owns; it will never reach Cloud Trace however it is configured.

The flush matters more than throughput here: a remediation is a handful of
spans, but the process carrying them is often a Cloud Run job or a pull-based
worker that exits as soon as the run finishes, so an unflushed batch is a lost
trace.

## Where spans go

`PATCHAPI_TRACE_EXPORTER` accepts `auto`, `cloud`, `console`, or `none` and
defaults to `auto`.

`auto` resolves to Cloud Trace whenever `GCP_PROJECT` or `GOOGLE_CLOUD_PROJECT`
is set and `opentelemetry-exporter-otlp-proto-grpc` is installed, and to the
console otherwise — so the same image traces to Cloud Run's Agent Observability
and to stdout on a laptop with no per-environment code path. `cloud` asks for
Cloud Trace explicitly and logs a warning when it is unavailable, because silence
there would hide a deployment that looks instrumented and exports nothing. An
unrecognised value warns and falls back to `auto`.

Cloud export is **OTLP over gRPC to the Telemetry API**
(`telemetry.googleapis.com`), authenticated as the workload with application
default credentials attached per call so a worker that outlives its access token
keeps exporting. The older `opentelemetry-exporter-gcp-trace` /
`CloudTraceSpanExporter` is deprecated and is not used. Exporting OTLP also means
spans are not reshaped on the way out: semantic-convention keys survive
verbatim, which is what makes the same trace readable outside Google Cloud.

`gcp.project_id` is set explicitly on the resource rather than left to
detection. On Cloud Run the detector supplies it, but a local run against a real
project has no metadata server, and the Telemetry API rejects a span it cannot
route with `INVALID_ARGUMENT`.

`BatchSpanProcessor` for Cloud Trace, because each export is a network round trip
that must not sit on the run's critical path; `SimpleSpanProcessor` for the
console, so a crashed run still leaves the trace that explains why.

## What a run's trace looks like

One parent span per run and one per pipeline stage, all pinned in `config.py`:

```text
patchapi.run
  patchapi.change_intelligence
  patchapi.impact
  patchapi.policy
  patchapi.patch
  patchapi.sandbox
  patchapi.verification
  patchapi.pull_request
```

ADK's own `invocation`, `invoke_agent`, `call_llm`, `generate_content`, and
`execute_tool` spans nest underneath whichever stage caused them, because
`agents/observe.py` makes the stage span current across the stage's awaits.
Without the parent, one remediation would arrive at the backend as seven
unrelated traces.

Attribute keys are prefixed `patchapi.` so they cannot collide with
OpenTelemetry semantic conventions, and `agents/observe.py` accepts only those
keys and only identifier-shaped values. A trace leaves the trust boundary, so
what may ride on one is deliberately narrow.

## Failure posture

Nothing here may fail a run. An unreachable backend, a missing exporter, a
credential problem, or a flush timeout is logged and swallowed; every path
degrades to a working provider or to a span that records nothing.

Verified by `./scripts/verify_packages_remaining.sh`, which asserts a span name
appears in captured console-exporter output, and by
`./scripts/verify_agent_image_closure.sh`, which asserts this package is present
in the agent lane image and reports Cloud Trace as reachable under the
deployment's environment.
