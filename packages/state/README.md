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
| `gcp_catalog.py` | Google Cloud service snapshot (Service Usage `services.list`) |
| `google_models.py` | Gemini / Vertex model snapshot (deprecation pages + list APIs) |
| `google_release_notes.py` | Last 365 days of the public BigQuery release-notes table |
| `provider_routes.py` | `GET /api/providers/google` and `/google/changes` |
| `secrets.py` | `project_secrets` names and pointers; never a value column |
| `secret_manager.py` | Secret Manager create / rotate / delete / reveal |
| `data/google_services.json` | Committed Service Usage snapshot (stand-in for Postgres) |
| `data/google_models.json` | Committed Gemini / Vertex lifecycle snapshot |
| `data/google_release_notes.json` | Local/bootstrap cache (gitignored; `scripts/fetch_google_release_notes.py`) |

How those files are downloaded: root [`README.md`](../../README.md) § Provider catalog snapshots.

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

`DATABASE_URL` is the only required setting. Local development uses Cloud SQL
through the Auth Proxy (same instance as Cloud Run):

```bash
./scripts/run_cloud_sql_proxy.sh
./scripts/serve_control_api.sh
```

`db/docker-compose.yml` remains for offline `./scripts/verify_db.sh` only.

## Tests

```bash
uv run pytest packages/state
```

The unit tests cover row mapping without a database. The queries themselves are
exercised against real Postgres by `scripts/verify_control_api_reads.sh`, which
skips rather than fails when Docker is unavailable — a skipped integration check
is honest, a passing one that never connected is not.
