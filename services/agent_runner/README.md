# patchapi-agent-runner

The Change Intelligence lane. Subscribes to `change-normalized` and attaches
rationale and a proposed replacement to a change event that already has a
status.

## What it may write

One statement, in `packages/state/enrichment.py`, touching four columns:
`summary`, `replacements`, `migration`, `source_urls`. The status columns and
`project_change_findings` are absent from it, so nothing this service produces
can move a finding into or out of Need you. Naming a replacement does not clear
`fail_closed` — a proposal is not a verification.

## Why every failure is a skip

The deterministic lane has already produced a correct finding by the time an
event arrives here. A missing notice, an unavailable model, or an agent that
asks for a human are all acked rather than retried: redelivering a turn that
refused for a good reason only spends tokens to refuse again.

## Running it

```bash
uv run patchapi-agent-runner-serve      # PORT=8080, POST /v1/events
```

Needs `DATABASE_URL`, `GCP_PROJECT`, and application default credentials with
Vertex access. `PATCHAPI_FEED_DIR` points at the provider notice documents
(`demo/fixtures` in the image).

## Tests

```bash
uv run pytest services/agent_runner/tests -q
```
