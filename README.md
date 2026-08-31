# PatchAPI

**Dependabot for APIs.** When an external API changes, PatchAPI finds the
affected code, generates and verifies a migration in an isolated environment,
and opens an evidence-backed pull request for normal human review.

Built for the [All Things Agentic Hackathon](https://allthingsagentichackathon.devpost.com/)
— Fortified Enterprise Fleet track.

Demo: [`amelia751/storygen`](https://github.com/amelia751/storygen).

## Architecture Diagram

![PatchAPI architecture](docs/architecture.png)

Three lanes share one Postgres store and stop at a pull request.

**Provider.** Google Cloud service endpoints and release notes feed a Cloud Run
+ ADK job (`patchapi-agents`). The Change Intelligence Agent writes a Change
Manifest. Provider text is untrusted; Model Armor screens intake.

**Developer.** A GitHub App imports a repository into the Next.js console
(`patchapi-web`). Identity Platform handles sign-in. The console talks to the
FastAPI control plane (`patchapi-api`) over SSE. Import and push events go
through Pub/Sub to `patchapi-indexer`, which scans with Zoekt and ast-grep and
stores findings as Needs you, Watching, or Dismissed.

**Agent fleet.** Starting remediation hands the finding to
`patchapi-remediate-worker` (Cloud Run worker pool, ADK + Vertex, Gemini 3.5
Flash). A Patch Agent proposes a change; a separate Verification Agent grades
it. Generated code runs only in a GKE Agent Sandbox under gVisor. Secrets stay
in Secret Manager. A passing run opens a GitHub pull request.

## Layout

```
.
├── README.md
├── pyproject.toml            uv workspace (Python 3.12)
├── uv.lock
├── Makefile
├── .env.example
├── cloudbuild.agents.yaml    agent-lane image
├── cloudbuild.ghtools.yaml   github-tools image
│
├── .github/workflows/
│   └── deploy-cloud-run.yml  push to main → Cloud Run
│
├── apps/web/                 patchapi-web · Next.js console
│   └── src/app/
│       ├── page.tsx          workspace  /
│       ├── provider/         provider portal
│       ├── changes/          findings inbox
│       ├── impact/
│       ├── runs/             [runId]
│       ├── fleet/
│       ├── settings/
│       └── auth/action/
│
├── services/
│   ├── control_api/          patchapi-api · FastAPI
│   │   └── routes/           health, providers, changes,
│   │                         runs, repositories, fleet,
│   │                         GitHub webhooks
│   ├── repo_indexer/         patchapi-indexer · Pub/Sub worker
│   │   ├── zoekt/            regex recall
│   │   ├── astgrep/          call-site confirmation
│   │   └── rules/<provider>/ one rule set per provider
│   ├── github_tools/         patchapi-github-tools
│   │   └── routes/           MCP + 10 capabilities
│   │                         (no merge / admin / secrets)
│   └── agent_runner/         patchapi-remediate-worker
│       └── remediation/      claim RECEIVED rows, slices,
│                             checkout, sandbox, PR
│
├── agents/                   Google ADK fleet
│   ├── orchestrator.py       orchestrator state machine
│   ├── specialists/          change_intelligence, impact,
│   │                         patch, verification
│   ├── tools/                change, impact, patch, policy, pr
│   └── fixtures/             pinned change manifests
│
├── packages/                 shared Python libraries
│   ├── schemas/              ChangeManifest, ImpactReport,
│   │                         PolicyDecision, PatchPlan,
│   │                         VerificationReport
│   ├── providers/            descriptors + ingest adapters
│   ├── policy/               injection gate + Model Armor
│   ├── state/                Cloud SQL / Postgres
│   ├── events/               Pub/Sub envelopes
│   ├── github/               capability enum (no tokens)
│   ├── repo_scan/            identifier inventory
│   ├── memory/               Vertex Memory Bank
│   ├── observability/        OTLP → Cloud Trace
│   ├── platform/             Agent Registry
│   └── auth/                 Identity Platform, OAuth
│
├── skills/                   ADK Agent Skills the Patch agent loads
│   ├── api-migration/        method for any provider migration
│   └── google-genai-migration/  Google request surfaces + traps
│
├── sandbox/
│   ├── runner/               isolated apply / build / test
│   └── gke/                  Agent Sandbox + gVisor
│
├── db/
│   ├── migrations/           0001–0024  (users → audit)
│   └── seeds/                console + Google provider
│
├── infra/terraform/
│   ├── environments/         dev, demo
│   └── modules/              Cloud Run, Cloud SQL, GKE,
│                             Pub/Sub, secrets, registry
│
├── demo/fixtures/            two storygen-relevant notices
├── docs/architecture.png
├── scripts/                  bootstrap, smoke, verify
└── tests/                    integration + fixtures
```

`demo/fixtures/` is not the production feed. In the full flow Change
Intelligence would read every BigQuery release note and write a
ChangeManifest — a year of notes is thousands of rows and a lot of tokens —
so the demo extracts the two notices that actually hit
[`storygen`](https://github.com/amelia751/storygen) (Gemini 2.0 Flash
shutdown, Imagen 4 retirement). The refresh job still pulls the rest of the
corpus into Postgres without a model. To backfill that locally:

```bash
uv run --all-packages python scripts/refresh_releases.py
```

## Spin-up Instructions

Judges can use the [live console](https://patchapi-web-913371146929.us-central1.run.app) without installing anything. The steps below are how to reproduce the same stack locally, or stand it up in your own GCP project.

### Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node 20+ and npm
- `psql` on `PATH` (`brew install libpq`) — the migration runner shells out to it
- `gcloud` authenticated against a project with billing
- Docker (only if you want offline Postgres instead of Cloud SQL)

### Local

1. Clone and install.

```bash
git clone https://github.com/amelia751/patch.git
cd patch
uv sync
cd apps/web && npm ci && cd ../..
```

2. Fill secrets. `.env.example` documents every variable; the serve scripts read `.secrets/` (gitignored) directly, so `.env` itself is only needed by the smoke scripts under `scripts/`.

```bash
cp .env.example .env
# write .secrets/gcp-service-account.json
# write .secrets/identity-platform.json
# write .secrets/github-app.pem and .secrets/github-app.json
```

3. Point local processes at Cloud SQL (same instance Cloud Run uses). `.secrets/database-url-proxy.txt` holds the DSN; on a new project, `./scripts/bootstrap_cloud_sql.sh` creates the instance and writes that file. The first run of the proxy script downloads the binary.

```bash
./scripts/run_cloud_sql_proxy.sh          # 127.0.0.1:5433
DATABASE_URL=$(cat .secrets/database-url-proxy.txt) \
  PYTHONPATH=db/src uv run python -m patchapi_db migrate
```

`DATABASE_URL` is not optional here: with it unset the runner targets the Docker compose container instead, which is not what sign-in uses. For that offline path, `docker compose -f db/docker-compose.yml up -d` and follow `db/README.md`.

4. Start the control plane. This also starts the Cloud SQL proxy if it is not already up, and two local remediation workers.

```bash
./scripts/serve_control_api.sh            # http://127.0.0.1:8080
```

5. Start the console.

```bash
# apps/web/.env.local — NEXT_PUBLIC_API_URL defaults to :8000, which is the wrong port
#   NEXT_PUBLIC_API_URL=http://127.0.0.1:8080
cd apps/web && npm run dev                # http://localhost:3000
```

Sign-in is server-side: the browser calls the control plane, which talks to Identity Platform using the key from `.secrets/`. The console needs no Identity Platform key of its own.

Sign in, connect GitHub, import a repo. The indexer and a full remediation need the remaining Cloud Run services (or their local counterparts in `scripts/`). `make test` and `make verify` run without them.

### Cloud

One-time bootstrap on an empty project, then every push to `main` deploys.

```bash
export GCP_PROJECT=your-project
export GCP_REGION=us-central1
export GOOGLE_APPLICATION_CREDENTIALS=.secrets/gcp-service-account.json

./scripts/bootstrap_cloud_sql.sh          # instance patchapi-console
./scripts/bootstrap_cloud_run.sh          # reserve URLs, WIF, Artifact Registry
./scripts/bootstrap_repo_indexer.sh
./scripts/bootstrap_github_tools.sh
./scripts/bootstrap_remediation_worker.sh
./scripts/bootstrap_release_refresh.sh

./scripts/run_cloud_sql_proxy.sh          # seeding goes through the proxy
./scripts/seed_google_provider.sh         # migrations + the Google provider row
```

Enable Identity Platform (email/password + Google), add the Cloud Run hosts as authorized domains, and create a GitHub App whose callback and webhook point at `patchapi-api`. Then push to `main`. `.github/workflows/deploy-cloud-run.yml` migrates Cloud SQL and deploys `patchapi-web`, `patchapi-api`, `patchapi-indexer`, `patchapi-agents`, `patchapi-github-tools`, and the warm worker pool.

Terraform under `infra/terraform/environments/dev` plans the supporting GCP surface (APIs, identities, Pub/Sub, secrets). GKE Agent Sandbox, the private Cloud SQL instance, and extra Cloud Run services are behind flags — see `infra/terraform/README.md`. The live demo uses the bootstrap scripts above plus the GitHub Actions workflow, not a full `terraform apply`.
