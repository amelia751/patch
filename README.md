# PatchAPI

**Dependabot for APIs.** When an external API changes, PatchAPI finds the
affected code, generates and verifies a migration in an isolated environment,
and opens an evidence-backed pull request for normal human review.

Built for the [All Things Agentic Hackathon](https://allthingsagentichackathon.devpost.com/)
— Fortified Enterprise Fleet track.

## Status

Early scaffold. Authoritative plan: [`roadmap.md`](./roadmap.md).

Flagship demo target: pinned fork of [`remorses/egaki`](https://github.com/remorses/egaki),
migrating Google Imagen 4 → Gemini 3.1 Flash Image. Second demo:
[`amelia751/storygen`](https://github.com/amelia751/storygen) (retired
`gemini-2.0-flash` + `imagen-4.0-generate-001`).

## Hosted console (stable Cloud Run)

These names are the URL. Do not rename or delete the services.

| | URL |
|---|---|
| Frontend | https://patchapi-web-913371146929.us-central1.run.app |
| Backend | https://patchapi-api-913371146929.us-central1.run.app |
| Repo indexer | https://patchapi-indexer-913371146929.us-central1.run.app |
| GitHub webhook | https://patchapi-api-913371146929.us-central1.run.app/v1/github/webhooks |
| Storygen (artful-journey) | https://storygen-1005432364863.us-central1.run.app |

Same services also answer at the classic `*.a.run.app` aliases. Prefer the
links above. Region is `us-central1`. Push to `main` deploys the PatchAPI
names (`.github/workflows/deploy-cloud-run.yml`). Storygen lives in project
`artful-journey-486915-a8`. Pushes to `main` on
[`amelia751/storygen`](https://github.com/amelia751/storygen) deploy with
the development key (`GCP_SA_KEY`). Manual:
[`demo/storygen/deploy.sh`](./demo/storygen/deploy.sh).

Local remains `http://localhost:3000` (dashboard) and `http://localhost:8080`
(control API).

### Repository indexer (Cloud Run + Pub/Sub)

`patchapi-indexer` is an always-on **push worker**, not a Cloud Run Job and not
a laptop process. Closing the dashboard does not stop it. Code:
[`services/repo_indexer/`](./services/repo_indexer/). Bootstrap:
[`scripts/bootstrap_repo_indexer.sh`](./scripts/bootstrap_repo_indexer.sh).

| | |
|---|---|
| Service | `patchapi-indexer` (`us-central1`) |
| Push URL | `https://patchapi-indexer-uhkx74fgmq-uc.a.run.app/v1/events` |
| SA | `patchapi-indexer@patch-505223.iam.gserviceaccount.com` |
| Invoker | `patchapi-pubsub-push@patch-505223.iam.gserviceaccount.com` |
| Image | `us-central1-docker.pkg.dev/patch-505223/patchapi/indexer` |
| SQL | Same instance `patchapi-console` (`provider_usages`, `repo_index_state`) |
| Git clone | Short-lived GitHub App installation token (PEM mounted; App key never in git) |

**Queue.** One Pub/Sub message is one `(repository, branch)` job. Importing a
second repo while the first is indexing, or pushes to both, waits in the
subscription. Cloud Run concurrency is 4; different repos run in parallel.
The same repo+branch takes a Postgres advisory lock so two deltas cannot
interleave.

| Event | Publisher | Worker |
|---|---|---|
| `project-repo-added` | Console after an import row commits | Full index of that branch |
| `repo-push` | `POST /v1/github/webhooks` (`push`) | Delta index; drop if no project imports the ref |
| `project-repo-removed` | Console after the row is gone | Decrement shard `reference_count` |

**What the UI shows.** The orange **Indexing codebase** bar is on a **project
Code tab**, not `/provider`. The file tree still loads from GitHub immediately;
the bar is `repo_index_state` over SSE (`GET /api/projects/{id}/events`) with
a poll fallback. Import marks the target `indexing` at 0% so the bar appears
before the first clone.

**Durable vs local.** Inventory rows live in Cloud SQL. Zoekt shards and git
mirrors live on the container disk for that revision; a cold start rebuilds
them. Postgres remains the source of truth.

**Local worker** (needs `DATABASE_URL` and the same topics, or a publish you
drive by hand):

```bash
uv run --package patchapi-repo-indexer patchapi-repo-indexer-serve
```

## Google Cloud

Project **`patch-505223`** (number `913371146929`). Compute and hosting are
**`us-central1`**. Gemini model IDs on this project resolve under Vertex
**`locations/global`** — they 404 in `us-central1`. See [`setup.md`](./setup.md)
§8 and [`.env.example`](./.env.example).

Google ADK is the agent runtime (hard constraint: no LangChain / LangGraph in
the product path). Reasoning model: **Gemini 3.5 Flash**. Flagship migration
target: **Imagen 4 → Gemini 3.1 Flash Image**.

### In use

| Service | What |
|---|---|
| Cloud Run | `patchapi-web` (dashboard), `patchapi-api` (control plane), `patchapi-indexer` (Pub/Sub push worker). Push to `main` deploys via `.github/workflows/deploy-cloud-run.yml`. |
| Artifact Registry | `us-central1-docker.pkg.dev/patch-505223/patchapi` — web, api, and indexer images. |
| Cloud SQL (Postgres 16) | Instance `patchapi-console`. Authoritative workflow state (constraint 7). Local talks to it through the Cloud SQL Auth Proxy (`127.0.0.1:5433`). |
| Secret Manager | Platform: `patchapi-database-url`, `patchapi-identity-api-key`, `patchapi-session-secret`, Google OAuth client id/secret, GitHub webhook HMAC, GitHub App client id/secret/App ID/PEM. Customer payloads: `patchapi-ps-*` (project secrets) and `patchapi-gcp-*` (Connect GCP JSON). Values never land in the repo. |
| Identity Platform | Email/password and Google sign-in (`identitytoolkit.googleapis.com`). Firebase auth domain `patch-505223.firebaseapp.com`. |
| Google OAuth | Web client in APIs & Services → Credentials. Continue with Google; origins/redirects below. |
| IAM + Workload Identity Federation | Pool `github-actions` / provider `github`. GitHub Actions impersonates `patchapi-github-deploy@…` — no JSON key in CI. Workload SAs: `patchapi-web@…`, `patchapi-api@…`, `patchapi-indexer@…`. Pub/Sub push uses `patchapi-pubsub-push@…`. |
| Vertex AI / Gemini Enterprise Agent Platform | `aiplatform.googleapis.com`. `gemini-3.5-flash` (agent reasoning) and `gemini-3.1-flash-image` (demo image path). |
| Memory Bank | Agent Engine resource created; name in `.secrets/memory_bank_name.txt`. Institutional context, not run state. |
| Cloud Logging | Cloud Run service accounts write logs. |
| Pub/Sub | Topics `patchapi-dev-{repo-push,project-repo-added,project-repo-removed,index-updated}`. Push subscriptions `*-sub` deliver to the indexer. |

### Enabled, not on the request path yet

APIs are on in the project. These are not serving console traffic today.

| Service | Role when wired |
|---|---|
| GKE Agent Sandbox | Isolated patch execution (gVisor). Local temp workspace stands in until then. |
| Cloud Storage | Run evidence bucket. |
| Model Armor | Sanitize untrusted provider text. |
| Agent Registry / Agent Gateway / Agent Identity | Fleet discovery, egress deny-by-tool, SPIFFE per agent. |
| Cloud Trace | One OTLP trace per remediation run. |
| Cloud Scheduler | Provider-check polling. |
| Cloud Build | Optional; GitHub Actions builds images today. |

Terraform for the same surface: [`infra/terraform/README.md`](./infra/terraform/README.md)
(`dev` plans clean; gated GKE / SQL / Run modules are off there because those
were bootstrapped with `./scripts/bootstrap_cloud_run.sh` and
`./scripts/bootstrap_cloud_sql.sh`). Full service list: `roadmap.md` §20–§21.

### Provider registry

`/provider` registers vendors and connects ingest URLs. Postgres is the
read model. A page load does not crawl Google. Plan: [`provider.md`](./provider.md).

Seed Google Cloud (no org owner) onto local Docker or Cloud SQL:

```bash
./scripts/run_cloud_sql_proxy.sh          # 127.0.0.1:5433 → patchapi-console
./scripts/seed_google_provider.sh         # migrate 0008 + upsert google
```

`seed_google_provider.sh` writes the profile only. Connect the two endpoints
in the portal by pasting one URL each:

| Tab | Example URL |
|---|---|
| Services | `https://serviceusage.googleapis.com/v1/projects/patch-505223/services` |
| Changes | `https://console.cloud.google.com/bigquery?p=bigquery-public-data&d=google_cloud_release_notes&t=release_notes` |

Connect returns immediately (`pending`). Ingest runs in the background:

- **Catalog** lists `state:ENABLED` first-party APIs (one or two pages). It does
  not crawl `--available` at 1 QPS.
- **Changes** is one BigQuery job against the pasted table. Billing project is
  the PatchAPI service account.

**Google Cloud services** — Service Usage
[`services.list`](https://cloud.google.com/service-usage/docs/list-services)
(`serviceusage.googleapis.com`).

| | |
|---|---|
| Endpoint | `GET https://serviceusage.googleapis.com/v1/projects/{project}/services?filter=state:ENABLED` |
| Auth | Project service account (`.secrets/gcp-service-account.json` or `GOOGLE_APPLICATION_CREDENTIALS`) |
| Keep | First-party hosts ending in `.googleapis.com` |
| Drop | Marketplace listings (`*.endpoints.*.cloud.goog`) |
| Persist | `provider_services` (not a JSON file) |

Service Usage titles are enable-an-API labels (`AlloyDB API`). The store
keeps the product name (`AlloyDB`). The host stays on the identifier
(`alloydb.googleapis.com`).

**Gemini / Vertex models** — two official HTML tables plus two list APIs.
The list APIs have launch stage / preview; they do not return retirement dates.

| Source | What it gives |
|---|---|
| [Gemini API deprecations](https://ai.google.dev/gemini-api/docs/deprecations) | Shutdown dates and replacements (HTML tables) |
| [Vertex model versions and lifecycle](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions) | Retirement dates and replacements (HTML tables) |
| Gemini [`models.list`](https://ai.google.dev/api/models) `GET https://generativelanguage.googleapis.com/v1beta/models` | Currently served Gemini API models (`.secrets/gemini_api_key.txt` or `GOOGLE_API_KEY`) |
| Vertex [`publishers.models.list`](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1beta1/publishers.models/list) `GET …/v1beta1/publishers/google/models` (global and `us-central1`) | Model Garden / Vertex models, including `launchStage` (same service account) |
| Snapshot | [`packages/state/data/google_models.json`](./packages/state/data/google_models.json) |
| Refresh | `refresh_google_models` in [`packages/state/google_models.py`](./packages/state/google_models.py) |

`GET /api/providers/google` serves the Service Usage file plus Gemini / Vertex
`models`. Model lifecycle rows with a day-precision shutdown date stay on
`modelChanges`. Month-only strings stay on the model and are not turned into
a date.

**Release notes (Changes tab)** — not Service Usage. The public BigQuery table
is one job (~5s for the last 365 days), not a 1 QPS list, and a year is
thousands of rows of changelog text. Do not fetch this when someone opens the
tab; refresh writes a file.

| | |
|---|---|
| Table | `bigquery-public-data.google_cloud_release_notes.release_notes` |
| Window | Last 365 days (~12k rows / ~8MB raw; snapshot stores stripped text) |
| Auth | Same project service account (queries bill to `patch-505223`) |
| Types | FEATURE, NON_BREAKING_CHANGE, FIX, SERVICE_ANNOUNCEMENT, SECURITY_BULLETIN, ISSUE, DEPRECATION, LIBRARIES, BREAKING_CHANGE, OTHER |
| Not in the table | Typed `{service, status, shutdown_date}` — descriptions are HTML changelog |
| Persist | `provider_change_notes` after Connect |
| Refresh | `fetch_release_notes` in [`packages/state/google_release_notes.py`](./packages/state/google_release_notes.py) |
| Serve | `GET /api/providers/{slug}/changes` |

RSS (`https://cloud.google.com/feeds/gcp-release-notes.xml`) is a 30-entry
Atom window, not the bulk table. Use it later as a delta, not as the catalog.

## GitHub: OAuth login + import App

Create **one** GitHub App (not a separate OAuth App). The App’s user-to-server
OAuth is Continue with GitHub; its installation id is repo import
(`github_connections`). Tokens never go in Postgres.

[Register a new GitHub App](https://github.com/settings/apps/new) on the
`amelia751` account:

| Field | Value |
|---|---|
| GitHub App name | `PatchAPI` (or `PatchAPI Demo` if taken) |
| Homepage URL | `https://patchapi-web-913371146929.us-central1.run.app` |
| Callback URL | `https://patchapi-api-913371146929.us-central1.run.app/api/auth/github/callback` |
| Callback URL (local) | `http://localhost:8080/api/auth/github/callback` |
| Setup URL | `https://patchapi-api-913371146929.us-central1.run.app/api/auth/github/setup` |
| Redirect on update | checked |
| Webhook URL | `https://patchapi-api-913371146929.us-central1.run.app/v1/github/webhooks` |
| Webhook active | **on** — HMAC-verified; unsigned deliveries are refused |
| Expire user authorization tokens | checked |
| Request user authorization (OAuth) during installation | checked |
| Where can this GitHub App be installed? | Any account |

Also add `http://127.0.0.1:8080/api/auth/github/callback` as a callback if the
form allows a third URL.

**Account permissions:** Email addresses → Read-only (login).

**Repository permissions** ([`roadmap.md`](./roadmap.md) §14):

| Permission | Access |
|---|---|
| Metadata | Read-only |
| Contents | Read and write |
| Pull requests | Read and write |
| Checks | Read-only |
| Administration, Secrets, Workflows, Deployments | No access |

**Subscribe to events:** `push`, `pull_request`, `installation`,
`installation_repositories`. The control plane indexes on `push`; the others
are acknowledged and ignored until a later subscriber exists.

After create:

1. Generate a private key. Move the PEM to `.secrets/github-app.pem` (`chmod 600`).
2. Copy App ID, Client ID, and Client secret into `.secrets/github-app.json`:

```json
{
  "app_id": 0,
  "client_id": "Iv1...",
  "client_secret": "...",
  "app_slug": "patchapi"
}
```

3. Generate a webhook secret and put it in
   `.secrets/github-webhook-secret.txt`. Cloud Run reads the same value from
   Secret Manager (`patchapi-github-webhook-secret` → `PATCHAPI_GITHUB_WEBHOOK_SECRET`).
4. Copy the App blob and PEM into Secret Manager (never commit them):

   ```bash
   ./scripts/sync_github_app_secrets.sh
   ```

   That writes `patchapi-github-app` (the JSON blob),
   `patchapi-github-oauth-client-id`, `patchapi-github-oauth-client-secret`,
   `patchapi-github-app-id`, and `patchapi-github-app-private-key`. The next
   push to `main` mounts them on `patchapi-api`.
5. Do **not** install the App on every repo yet. Install it on
   `amelia751/egaki` (and later whatever the console imports).

Env the control plane will read (see `.env.example`):

```text
GITHUB_APP_ID=
GITHUB_APP_SLUG=patchapi
GITHUB_APP_PRIVATE_KEY_PATH=.secrets/github-app.pem
PATCHAPI_GITHUB_OAUTH_CLIENT_ID=
PATCHAPI_GITHUB_OAUTH_CLIENT_SECRET=
PATCHAPI_GITHUB_OAUTH_REDIRECT_URI=http://localhost:8080/api/auth/github/callback
```

On Cloud Run the redirect URI is
`https://patchapi-api-913371146929.us-central1.run.app/api/auth/github/callback`
and the PEM is mounted at `/var/github/app.pem`. Public liveness is
`GET /health` — Cloud Run reserves `/healthz`.

### Google OAuth (already created)

Add the hosted origins to the existing Web client (APIs & Services →
Credentials). A service account cannot edit that client on this project:

| Field | Value |
|---|---|
| JavaScript origin | `https://patchapi-web-913371146929.us-central1.run.app` |
| Redirect URI | `https://patchapi-api-913371146929.us-central1.run.app/api/auth/google/callback` |

## Hard product boundary

PatchAPI **stops at the pull request**. It does not merge, deploy, edit branch
protection, or bypass CODEOWNERS / CI.

## Local agent fleet

Claude Code workforce tooling lives in `.fleet/` (gitignored). After cloning:

```bash
.fleet/bin/bootstrap.sh     # sync roles → .claude/agents, create ./fleet
./fleet doctor
./fleet roles
./fleet run smoke --dry-run
```

Project conventions for agents: [`CLAUDE.md`](./CLAUDE.md).
