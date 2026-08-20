# `db/` — console tenancy state

Postgres holds what the dashboard persists: who the user is, whether a GitHub
App is connected, which projects they imported, and secret *names* (not
values). Identity Platform holds passwords. GitHub holds tokens. Secret Manager
holds secret payloads.

PatchAPI workflow tables (runs, policy, patches, PRs) are not in this schema
yet. They come back as additive migrations when that product surface is wired.

## Layout

| Path | Purpose |
|---|---|
| `docker-compose.yml` | Local Postgres 16. The only Postgres service definition in the repo. |
| `migrations/` | Forward-only `NNNN_slug.sql` scripts. Never edited after they apply. |
| `seeds/` | Re-runnable demo data, clearly labelled as seed. |
| `src/patchapi_db/` | Discovery, checksumming, and application of the scripts above. |
| `tests/` | Offline checks on the SQL corpus; no database required. |

## Running it

Day-to-day local work uses **Cloud SQL** (`patchapi-console`), the same
instance Cloud Run uses. Docker Compose is the offline verifier only.

```bash
./scripts/run_cloud_sql_proxy.sh          # 127.0.0.1:5433 → Cloud SQL
./scripts/serve_control_api.sh            # loads .secrets/database-url-proxy.txt
PYTHONPATH=db/src uv run python -m patchapi_db migrate
PYTHONPATH=db/src uv run python -m patchapi_db status
```

```bash
docker compose -f db/docker-compose.yml up -d   # offline verify_db.sh only
export PYTHONPATH=db/src
uv run python -m patchapi_db migrate
uv run python -m patchapi_db seed
uv run python -m patchapi_db status
uv run python -m patchapi_db sql

./scripts/verify_db.sh
```

`uv run --package patchapi-db python -m patchapi_db …` works too, and installs
the member into the shared workspace environment. The `PYTHONPATH` form above
is used by the verifier so that running it does not change what other trees in
the workspace have installed.

The runner has no database driver dependency: it discovers and orders the SQL,
then hands it to `psql`. With `DATABASE_URL` set it uses a local `psql` client
against that DSN — the Cloud SQL path, via the Auth Proxy. With `DATABASE_URL`
unset it runs `psql` inside the compose container, so a developer needs Docker
but not a matching client install.

## Tables

```text
users
user_identities
github_connections
projects
project_repositories
workspaces
project_secrets
providers
provider_connections
provider_services
provider_change_notes
project_provider_subscriptions
```

| Table | Role |
|---|---|
| `users` | Console profile. `identity_platform_uid` links Identity Platform. No password column. |
| `user_identities` | Linked logins (`github` / `google`). Supplies `github_id` / `github_username`. |
| `github_connections` | GitHub App installation id only. `github_app_installed` means a row exists. |
| `projects` | `POST /api/projects/` — name, status, owner, optional `cloud_provider`. |
| `project_repositories` | Imported `owner/repo`. Listing live GitHub repos is an API call, not this table. |
| `workspaces` | `POST …/workspaces/import-repo` — clone URL, branch, optional subfolder. |
| `project_secrets` | Secret name + remote ARN/resource. Values stay in Secret Manager. |
| `gcp_connections` | Viewer SA email + Secret Manager pointer, scoped to a repo workspace. |

## Migration rules

1. **Forward-only.** To change an applied migration, add a new one. The runner
   records a SHA-256 of every migration and refuses to continue if the text of
   an applied one has changed.
2. **One concern per file.** The version is the four-digit filename prefix and
   determines apply order; versions are contiguous from `0001`.
3. **No transaction control inside a script.** The runner wraps each script and
   its ledger row in one transaction, so a failed migration leaves nothing.
4. **No business logic in triggers.** The only database-side logic is `CHECK`
   constraints.

## Constraints

| Constraint | Rule |
|---|---|
| `users.email` unique + must contain `@` | Profile email is a real address, not a display string |
| `users.settings` is a JSON object | Matches the `User.settings` blob the UI sends |
| `user_identities` unique `(provider, provider_user_id)` | One GitHub account cannot attach to two users |
| `github_connections.user_id` unique | One App installation per user for now |
| `project_repositories.full_name` is `owner/repo` | Import payload shape |
| `project_secrets` has no value column | Secret payloads never persist here |
| `gcp_connections` has no credentials column | Service-account JSON never persists here |

## Seed data

`seeds/0001_demo_console.sql` inserts a labelled demo user, a GitHub connection
for `amelia751`, and a draft project importing `amelia751/egaki`. Every seeded
row uses a UUID in the reserved `5eedda7a-` prefix.

`seeds/0002_google_provider.sql` upserts Google Cloud as a system provider
(no owner). Run `./scripts/seed_google_provider.sh` against Cloud SQL.
