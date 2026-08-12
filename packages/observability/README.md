# `packages/observability`

OpenTelemetry setup for PatchAPI agents and services (`roadmap.md` §14).

Instrumentation is standards-based, so the same spans reach Agent Observability
and Cloud Trace in Google Cloud and a console exporter locally, without the
instrumented code knowing which. Span and attribute names are pinned in
`config.py` so a rename is one visible change and a dashboard query cannot
quietly stop matching.

```python
from packages.observability import ATTR_RUN_ID, SPAN_POLICY, configure_tracing, span

provider = configure_tracing(service_name="patchapi-control-api")
with span(SPAN_POLICY, attributes={ATTR_RUN_ID: run_id}, provider=provider):
    ...
```

`configure_tracing` returns a provider instead of installing one globally unless
asked. OpenTelemetry ignores a second global provider, so a library that
installs one on import would silently win or lose depending on import order —
pass `install_globally=True` from a process entry point only.

Spans use `SimpleSpanProcessor`: a run is a handful of spans, and exporting as
each one ends means a run that crashes still leaves the trace explaining why.

Verified by `./scripts/verify_packages_remaining.sh`, which asserts a span name
appears in captured console-exporter output.
