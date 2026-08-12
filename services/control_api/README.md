# patchapi-control-api

The PatchAPI control plane (roadmap §7.2). It serves health probes, the manual
provider-check trigger, and deterministic run-state reads for the dashboard.

**It never executes repository code.** Patches are applied and tested in the
sandbox; this service only routes HTTP, validates input, and derives idempotency
keys. `tests/test_no_code_execution.py` enforces that against the source tree.

## Surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | Liveness. Touches no dependency; always 200 while serving. |
| `GET` | `/readyz` | Readiness per dependency. 503 until every probe is satisfied. |
| `POST` | `/v1/provider-checks` | Manual trigger to look for changes from one provider. |
| `GET` | `/v1/runs/{run_id}` | Deterministic run state plus the transitions still allowed. |

OpenAPI is served at `/openapi.json`, interactive docs at `/docs`.

## Dependency wiring

`create_app()` takes its dependencies as arguments:

```python
from patchapi_control_api import create_app

app = create_app(
    provider_check_dispatcher=pubsub_dispatcher,
    run_state_reader=postgres_reader,
)
```

Both ports are declared in `ports.py`. Until a port is supplied the service
fails closed: `/readyz` reports `not_ready` and the route that needs it returns
503 naming the missing dependency. It never answers from a cache or invents a
run status.

`patchapi_control_api.asgi:app` is the unwired ASGI target used by local
probes. The container entry point is `patchapi-serve` (packages/state), which
wires Postgres and `/api/auth/*` before serving.

## Idempotency

`POST /v1/provider-checks` derives its key from the provider and the requested
window, never from a caller-supplied value, so replaying the same trigger
converges on the same run (roadmap §9). Attribution (`requested_by`) is
excluded from the key: two engineers asking for the same work are asking for the
same work. Timestamps must be timezone-aware, otherwise the same request from
two machines would hash differently.

## Run and verify

```bash
uv run --package patchapi-control-api uvicorn patchapi_control_api.asgi:app --port 8080
./scripts/verify_services_control_api.sh
```

The verify script boots the real server on an ephemeral port, probes it over
HTTP, and tears it down.
