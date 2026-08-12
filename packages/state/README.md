# `packages.state`

Read-only access to PatchAPI's authoritative workflow state in Postgres.

Constraint 7: Postgres is the source of truth for run status, idempotency and
audit. This package is how a service *reads* that truth. It implements the
control plane's `RunStateReader` and `DashboardReader` ports against the schema
in `db/migrations/`.

## What lives here

| Module | Responsibility |
|---|---|
| `config.py` | DSN resolution from the environment, and pool sizing |
| `pool.py` | asyncpg pool lifecycle and JSON/numeric codecs |
| `runs.py` | `PostgresRunStateReader` — the narrow, pollable run-state read |
| `dashboard.py` | `PostgresDashboardReader` — the dashboard's read projections |

## What deliberately does not live here

**Writes.** Nothing in this package inserts, updates or deletes. Run state is
advanced by the orchestrator, not by anything serving a dashboard. A read model
that could write would make the control plane an execution surface, which
roadmap §7.2 forbids.

**Invented rows.** Every method returns what the store holds. An unknown run is
`None`, never an empty record; an unreachable database raises, and the route
turns that into a fail-closed 503. Neither is ever softened into an empty list
that a reader would mistake for "we looked and found nothing".

## Connecting

`DATABASE_URL` is the only required setting:

```bash
export DATABASE_URL='postgresql://patchapi:patchapi_local_dev@127.0.0.1:55432/patchapi'
```

That matches the defaults in `db/docker-compose.yml`. Bring the database up and
load the schema and demo rows with:

```bash
docker compose -f db/docker-compose.yml up -d
uv run patchapi-db migrate
uv run patchapi-db seed
```

## Tests

```bash
uv run pytest packages/state
```

The unit tests cover row mapping without a database. The queries themselves are
exercised against real Postgres by `scripts/verify_control_api_reads.sh`, which
skips rather than fails when Docker is unavailable — a skipped integration check
is honest, a passing one that never connected is not.
