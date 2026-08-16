# PatchAPI

**Dependabot for APIs.** When an external API changes, PatchAPI finds the
affected code, generates and verifies a migration in an isolated environment,
and opens an evidence-backed pull request for normal human review.

Built for the [All Things Agentic Hackathon](https://allthingsagentichackathon.devpost.com/)
— Fortified Enterprise Fleet track.

## Status

Early scaffold. Authoritative plan: [`roadmap.md`](./roadmap.md).

Flagship demo target: pinned fork of [`remorses/egaki`](https://github.com/remorses/egaki),
migrating Google Imagen 4 → Gemini 3.1 Flash Image.

## Hosted console (stable Cloud Run)

These names are the URL. Do not rename or delete the services.

| | URL |
|---|---|
| Frontend | https://patchapi-web-913371146929.us-central1.run.app |
| Backend | https://patchapi-api-913371146929.us-central1.run.app |
| GitHub webhook | https://patchapi-api-913371146929.us-central1.run.app/v1/github/webhooks |

Same services also answer at the classic `*.a.run.app` aliases. Prefer the
links above. Region is `us-central1`. Push to `main` deploys into these names
(`.github/workflows/deploy-cloud-run.yml`).

Local remains `http://localhost:3000` (dashboard) and `http://localhost:8080`
(control API).

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
| Cloud Run | `patchapi-web` (dashboard) and `patchapi-api` (control plane). Push to `main` deploys via `.github/workflows/deploy-cloud-run.yml`. |
| Artifact Registry | `us-central1-docker.pkg.dev/patch-505223/patchapi` — web and api images. |
| Cloud SQL (Postgres 16) | Instance `patchapi-console`. Authoritative workflow state (constraint 7). Local talks to it through the Cloud SQL Auth Proxy (`127.0.0.1:5433`). |
| Secret Manager | `patchapi-database-url`, `patchapi-identity-api-key`, `patchapi-session-secret`, `patchapi-github-webhook-secret`, Google OAuth client id/secret. Values never land in the repo. |
| Identity Platform | Email/password and Google sign-in (`identitytoolkit.googleapis.com`). Firebase auth domain `patch-505223.firebaseapp.com`. |
| Google OAuth | Web client in APIs & Services → Credentials. Continue with Google; origins/redirects below. |
| IAM + Workload Identity Federation | Pool `github-actions` / provider `github`. GitHub Actions impersonates `patchapi-github-deploy@…` — no JSON key in CI. Workload SAs: `patchapi-web@…`, `patchapi-api@…`. |
| Vertex AI / Gemini Enterprise Agent Platform | `aiplatform.googleapis.com`. `gemini-3.5-flash` (agent reasoning) and `gemini-3.1-flash-image` (demo image path). |
| Memory Bank | Agent Engine resource created; name in `.secrets/memory_bank_name.txt`. Institutional context, not run state. |
| Cloud Logging | Cloud Run service accounts write logs. |
| Pub/Sub | GitHub webhook publishes `repo-push` (and the console publishes repository membership events) onto `patchapi-dev-*` topics. |

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

### Provider catalog snapshots

The `/provider` console reads committed JSON, not Google, on each page load.
Postgres replaces those files later. Provider pages and list APIs are
untrusted input.

**Google Cloud services** — Service Usage
[`services.list`](https://cloud.google.com/service-usage/docs/list-services)
(`serviceusage.googleapis.com`).

| | |
|---|---|
| Endpoint | `GET https://serviceusage.googleapis.com/v1/projects/{project}/services` |
| Auth | Project service account (`.secrets/gcp-service-account.json` or `GOOGLE_APPLICATION_CREDENTIALS`) |
| Keep | First-party hosts ending in `.googleapis.com` |
| Drop | Marketplace listings (`*.endpoints.*.cloud.goog`) |
| Quota | `list_available_requests` defaults to 1 QPS — page slowly or the list 429s |
| Snapshot | [`packages/state/data/google_services.json`](./packages/state/data/google_services.json) |
| Refresh | `refresh_google_catalog` in [`packages/state/gcp_catalog.py`](./packages/state/gcp_catalog.py) |

Same list via CLI (also Service Usage):

```bash
gcloud services list --available --filter="config.name:googleapis.com"
```

Service Usage titles are enable-an-API labels (`AlloyDB API`). The snapshot
stores the product name (`AlloyDB`). The host stays on the identifier
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

Both snapshots are served together:

```text
GET /api/providers/google
```

`services` comes from the Service Usage file. `models` and `changes` come from
the Gemini / Vertex file. A change row is emitted only when the provider page
gave a day-precision shutdown or retirement date — month-only strings stay on
the model and are not turned into a date.

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
4. Do **not** install the App on every repo yet. Install it on
   `amelia751/egaki` (and later whatever the console imports).

Env the control plane will read (see `.env.example`):

```text
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY_PATH=.secrets/github-app.pem
PATCHAPI_GITHUB_OAUTH_CLIENT_ID=
PATCHAPI_GITHUB_OAUTH_CLIENT_SECRET=
PATCHAPI_GITHUB_OAUTH_REDIRECT_URI=http://localhost:8080/api/auth/github/callback
```

On Cloud Run the redirect URI is
`https://patchapi-api-913371146929.us-central1.run.app/api/auth/github/callback`.

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
