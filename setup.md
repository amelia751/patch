# PatchAPI — Setup Plan

> Review this document before dispatching the setup fleet.  
> Source of truth for layout: [`roadmap.md`](./roadmap.md) §6.  
> Source of truth for product constraints: [`CLAUDE.md`](./CLAUDE.md).

**Goal:** scaffold every monorepo tree, install real dependencies, and prove each tree works with a **dynamic smoke test** (not a static checklist). After approval, a fleet batch executes these tasks in parallel with hard path ownership so workers do not collide.

**Not in scope for this setup batch:** implementing the full migration product, opening production PRs, or polishing the 4-minute demo. This batch only makes the trees real and verifiable.

---

## 0. Current state (as of this draft)

| Path | Status |
|---|---|
| `apps/web/` | Next.js 16 app relocated from root `web/` (npm lockfile kept) |
| `demo/`, `docs/research/` | empty placeholders |
| Root Python workspace (`pyproject.toml`, `uv.lock`) | missing |
| `services/`, `agents/`, `packages/`, `skills/`, `sandbox/`, `db/`, `infra/`, `tests/` | missing |
| `.secrets/` | SA key + Gemini API key + smoke artifacts (gitignored) |

**Layout note:** `roadmap.md` §6 places the dashboard at `apps/web/`. The Next app has been relocated from root `web/` → `apps/web/` and stays on **npm** (project choice; overrides the roadmap’s pnpm preference for the dashboard). Egaki demo work may still use whatever the pinned fork uses.

Where [`CLAUDE.md`](./CLAUDE.md) says `apps/dashboard/`, prefer `apps/web/` from the roadmap; update `CLAUDE.md` when conventions are synced.

**GCP project for live smokes:** `patch-505223` (SA: `development@patch-505223.iam.gserviceaccount.com`, key in `.secrets/gcp-service-account.json`, gitignored).

---

## 1. Principles for every setup task

1. **Tree separation.** Each task owns exactly one top-level tree (or one named subtree). Workers must not edit outside their owned paths except to append their pass/fail line to a shared ledger file.
2. **Install for real.** Prefer pinned, installable packages. No fake “TODO package” stubs that cannot import.
3. **Dynamic verify.** Every task ships a `scripts/verify_<tree>.sh` (or `make verify-<tree>`) that fails non-zero when broken. Verification must execute code or call a live API — grepping for filenames is not enough.
4. **Secrets stay out of git.** Credentials live under `.secrets/` (gitignored) and are referenced via env vars from `.env.example`.
5. **Fail closed.** If Gemini / GCP / GitHub / GKE credentials are missing, the verify script exits with a clear `SKIP:` or `FAIL:` reason. Never invent a successful model call, sandbox result, or PR.
6. **Idempotent.** Re-running a setup task should converge, not duplicate resources or break a working tree.

### Shared ledger

All tasks append one line to:

```text
demo/setup-ledger.ndjson
```

Example line:

```json
{"task":"T-packages-schemas","status":"PASS","command":"uv run pytest packages/schemas/tests -q","at":"2026-08-11T23:00:00Z"}
```

---

## 2. Target tree (roadmap §6)

```text
patchapi/
├── README.md
├── roadmap.md
├── setup.md                 ← this file
├── pyproject.toml
├── uv.lock
├── Makefile
├── .env.example
│
├── apps/
│   └── web/                 ← relocate from existing web/
│
├── services/
│   ├── control_api/
│   ├── github_tools/
│   └── repo_indexer/
│
├── agents/
│   ├── orchestrator/
│   ├── change_intelligence/
│   ├── impact/
│   ├── policy/
│   ├── patch/
│   ├── verification/
│   └── pr/
│
├── packages/
│   ├── schemas/
│   ├── providers/google/
│   ├── github/
│   ├── repo_scan/
│   ├── policy/
│   ├── events/
│   ├── memory/
│   └── observability/
│
├── skills/
│   └── google_imagen_migration/
│
├── sandbox/
│   ├── runner/
│   └── gke/
│
├── db/
│   ├── migrations/
│   └── seeds/
│
├── infra/
│   └── terraform/
│
├── demo/
│   ├── fixtures/
│   ├── egaki/
│   └── adversarial/
│
├── docs/
│   ├── architecture.md
│   ├── architecture.png
│   ├── threat-model.md
│   ├── data-model.md
│   ├── agent-contracts.md
│   └── operations.md
│
├── tests/                   ← added for PatchAPI self-tests (roadmap §23)
│   ├── unit/
│   ├── integration/
│   ├── agent_eval/
│   └── adversarial/
│
└── scripts/
    └── verify_*.sh          ← one dynamic verifier per tree (or Makefile targets)
```

---

## 3. Prerequisites (human, before fleet)

Run once on the machine that will execute setup:

| Tool | Expected | Check |
|---|---|---|
| Python | 3.12+ | `python3 --version` |
| uv | recent | `uv --version` |
| Node | 20+ | `node --version` |
| npm | 10+ | `npm --version` |
| Docker | running | `docker info` |
| gcloud | authenticated | `gcloud auth list` |
| terraform | optional for infra tree | `terraform version` |
| GitHub CLI | for demo fork / App checks | `gh auth status` |

### Secrets contract (create under `.secrets/`, never commit)

| File / env | Used by |
|---|---|
| `GOOGLE_API_KEY` or ADC via `gcloud auth application-default login` | Gemini 3.5 Flash smoke, Gemini 3.1 Flash Image smoke |
| `GCP_PROJECT` / `GCP_REGION` (default `us-central1`) | GKE, Cloud Run, Artifact Registry |
| GitHub App private key + App ID + installation ID | `services/github_tools` live verify |
| `.secrets/gcp-service-account.json` (already present) | infra / sandbox if used |

Copy names into root `.env.example` without values.

---

## 4. Dependency DAG (fleet parallelism)

```text
Wave 0 (serial, one worker)
  T-root-workspace

Wave 1 (parallel, tree-separated)
  T-apps-web
  T-packages-*          (schemas first, then others after schemas lands)
  T-db
  T-demo-baseline
  T-docs-scaffold
  T-skills
  T-infra-terraform     (plan-only OK if no GCP apply yet)

Wave 2 (parallel; needs packages + root)
  T-services-control_api
  T-services-github_tools
  T-services-repo_indexer
  T-agents-adk
  T-sandbox-local

Wave 3 (needs GCP + Wave 2)
  T-gemini-live         (cross-cutting smoke; owns scripts/ only)
  T-sandbox-gke
  T-github-app-live     (optional if App not ready — must SKIP clearly)
  T-apps-web-browser    (Playwright against local Next)

Wave 4 (serial)
  T-qa-aggregate        (runs all verify_* ; writes setup report)
```

**Hard ownership rule:** a worker may write only under its `owns:` paths listed below. Cross-cutting scripts go in `scripts/` and are owned by the task that creates them.

---

## 5. Setup tasks (tree-separated)

Each task block is fleet-ready: role, owns, does, verify, pass criteria.

---

### T-root-workspace

| | |
|---|---|
| **Role** | `schema-engineer` (or backend) |
| **Owns** | `pyproject.toml`, `uv.lock`, `Makefile`, `.env.example`, `ruff.toml` / tool config, `scripts/verify_root.sh` |
| **Does** | Create uv workspace covering `packages/*`, `services/*`, `agents`, `db`. Pin Python 3.12. Add shared dev deps: `ruff`, `pytest`, `pytest-asyncio`. Makefile targets: `sync`, `lint`, `test`, `verify`. |
| **Dynamic verify** | `./scripts/verify_root.sh` → `uv sync` + `uv run python -c "import sys; assert sys.version_info[:2] == (3,12)"` + `uv run ruff check .` on owned paths |
| **Pass** | lockfile exists; `uv run pytest -q` discovers at least one placeholder test that passes |

---

### T-apps-web

| | |
|---|---|
| **Role** | `frontend-engineer` |
| **Owns** | `apps/web/**`, relocation of root `web/` → `apps/web/`, `scripts/verify_apps_web.sh` |
| **Does** | Relocate Next app to `apps/web/` (done). Keep **npm** (`package-lock.json`). TypeScript strict. Leave pages as scaffold; do not redesign UI in this batch. |
| **Dynamic verify** | `./scripts/verify_apps_web.sh` → `npm --prefix apps/web ci` → `npm --prefix apps/web run lint` → `npm --prefix apps/web run build` → start `npm --prefix apps/web start` briefly and `curl -fsS http://127.0.0.1:3000` returns HTTP 200 |
| **Pass** | production build succeeds; HTTP smoke against running server succeeds; root `web/` directory gone |

---

### T-apps-web-browser

| | |
|---|---|
| **Role** | `frontend-engineer` + `qa-verifier` |
| **Owns** | `apps/web/e2e/**`, `scripts/verify_apps_web_browser.sh` |
| **Depends** | T-apps-web |
| **Does** | Add Playwright (or project-standard browser runner) under `apps/web/e2e`. One smoke: home page loads, title/brand visible. |
| **Dynamic verify** | `./scripts/verify_apps_web_browser.sh` boots Next, runs Playwright, tears down |
| **Pass** | browser test exits 0; screenshot artifact under `apps/web/e2e/artifacts/` (gitignored OK) |

---

### T-packages-schemas

| | |
|---|---|
| **Role** | `schema-engineer` |
| **Owns** | `packages/schemas/**`, `scripts/verify_packages_schemas.sh` |
| **Does** | Pydantic models for versioned contracts named in roadmap §8: `ChangeManifest`, `ImpactReport`, policy decision, `PatchPlan`, `VerificationReport`, run-state enums. Pin schema versions in config, not call sites. |
| **Dynamic verify** | round-trip JSON → model → JSON for each contract using the Google deprecation fixture shape from roadmap §15.4; `uv run pytest packages/schemas` |
| **Pass** | invalid manifests raise ValidationError; fixture fixture loads |

---

### T-packages-providers-google

| | |
|---|---|
| **Role** | `schema-engineer` / `research-scout` for model IDs |
| **Owns** | `packages/providers/google/**`, `scripts/verify_packages_providers_google.sh` |
| **Depends** | T-packages-schemas, secrets for live call |
| **Does** | Adapter that loads pinned model IDs from config (`gemini-2.5` is wrong — default reasoning model is **Gemini 3.5 Flash**; image replacement is **`gemini-3.1-flash-image`**). Parser/normalizer for deprecation fixture → `ChangeManifest`. |
| **Dynamic verify** | (1) offline: fixture → manifest. (2) live: `uv run python -m packages.providers.google.smoke` calls Gemini 3.5 Flash with a tiny prompt and asserts non-empty text + model id in response metadata |
| **Pass** | offline always; live PASS or explicit `SKIP: missing GOOGLE_API_KEY/ADC` (not a silent fake) |

---

### T-packages-remaining

| | |
|---|---|
| **Role** | `schema-engineer` + `policy-engineer` + `backend-engineer` |
| **Owns** | `packages/github/**`, `packages/repo_scan/**`, `packages/policy/**`, `packages/events/**`, `packages/memory/**`, `packages/observability/**`, matching `scripts/verify_packages_*.sh` |
| **Does** | Minimal importable packages with interfaces matching roadmap: narrow GitHub types, deterministic repo scan helpers, forbidden-path policy, event envelope, Memory Bank client stub (interface + local fake), OpenTelemetry setup helper. |
| **Dynamic verify** | each package: import + one unit test. Policy package: assert `.github/workflows/release.yml` is BLOCKED. Observability: emit one span to console exporter and assert span name appears in captured output |
| **Pass** | all package verifiers exit 0 |

---

### T-services-control_api

| | |
|---|---|
| **Role** | `backend-engineer` |
| **Owns** | `services/control_api/**`, `scripts/verify_services_control_api.sh` |
| **Depends** | T-root-workspace, T-packages-schemas |
| **Does** | FastAPI app skeleton: health, ready, manual “check provider changes” stub endpoint, run-state read stub. Dockerfile. No untrusted code execution. |
| **Dynamic verify** | `uv run uvicorn` (or package entry) on ephemeral port → `curl /healthz` → JSON `{"status":"ok"}`; OpenAPI schema served at `/docs` or `/openapi.json` |
| **Pass** | health returns 200; process exits cleanly after probe |

---

### T-services-github_tools

| | |
|---|---|
| **Role** | `github-tools-engineer` |
| **Owns** | `services/github_tools/**`, `scripts/verify_services_github_tools.sh` |
| **Does** | Narrow capability surface from roadmap §7.3. Explicitly reject merge/admin/secret/branch-protection routes. Credentials loaded only from env/Secret Manager pattern. |
| **Dynamic verify** | (1) unit: capability allowlist test. (2) live optional: `get_repository_metadata` against demo fork if App creds present |
| **Pass** | calling a forbidden capability returns 403/structured error; live call PASS or `SKIP: GitHub App not configured` |

---

### T-services-repo_indexer

| | |
|---|---|
| **Role** | `backend-engineer` |
| **Owns** | `services/repo_indexer/**`, `scripts/verify_services_repo_indexer.sh` |
| **Does** | Worker skeleton that can scan a local checkout for Imagen 4 identifiers (deterministic Layer A from roadmap §11.3). |
| **Dynamic verify** | point indexer at a tiny fixture tree under `tests/fixtures/repo_with_imagen/` containing `imagen-4.0-generate-001`; assert inventory JSON lists that identifier |
| **Pass** | deterministic hit; empty tree yields empty inventory |

---

### T-agents-adk

| | |
|---|---|
| **Role** | `adk-agent-engineer` |
| **Owns** | `agents/**`, `scripts/verify_agents_adk.sh` |
| **Depends** | T-root-workspace, T-packages-schemas, T-packages-providers-google |
| **Does** | Google **ADK-only** orchestrator + six specialists as importable agent modules (`change_intelligence`, `impact`, `policy`, `patch`, `verification`, `pr`). Pin model id in config to Gemini 3.5 Flash. No LangChain/LangGraph/etc. |
| **Dynamic verify** | `uv run python scripts/smoke_adk_orchestrator.py` constructs the ADK app/agents, runs one tiny Change Intelligence turn on the local deprecation fixture, prints tool/agent trace |
| **Pass** | ADK imports succeed; smoke returns structured output validating as `ChangeManifest`; response metadata shows Gemini 3.5 Flash (or documented newer). If API key missing → `SKIP` with reason |

---

### T-db

| | |
|---|---|
| **Role** | `postgres-engineer` |
| **Owns** | `db/**`, `scripts/verify_db.sh` |
| **Does** | Alembic (or equivalent) migrations for run state, artifacts metadata, API usage inventory tables (roadmap §10.1). Seeds for local demo. Docker Compose snippet for local Postgres **owned here** as `db/docker-compose.yml` (not a second source of truth elsewhere). |
| **Dynamic verify** | `docker compose -f db/docker-compose.yml up -d` → migrate → seed → SQL query asserts expected tables exist and seed row count > 0 → down |
| **Pass** | migrations apply cleanly twice (idempotent); seed is re-runnable |

---

### T-sandbox-local

| | |
|---|---|
| **Role** | `sandbox-engineer` |
| **Owns** | `sandbox/runner/**`, `scripts/verify_sandbox_local.sh` |
| **Does** | Local temp-workspace runner: clone/copy pinned path, apply empty/no-op patch, run configurable install/build/test commands, collect logs. Early-phase stand-in before GKE. |
| **Dynamic verify** | run runner against a tiny Node or Python fixture repo under `sandbox/runner/testdata/`; assert exit 0 and `logs/build.txt` exists |
| **Pass** | isolation directory created under `/tmp` or configured workspace and deleted/retained per flag; no writes into the main checkout “as done” |

---

### T-sandbox-gke

| | |
|---|---|
| **Role** | `sandbox-engineer` + `cloud-infra-engineer` |
| **Owns** | `sandbox/gke/**`, sandbox runner Dockerfile publish scripts under `sandbox/runner/`, `scripts/verify_sandbox_gke.sh` |
| **Depends** | T-sandbox-local, T-infra-terraform (cluster or documented existing cluster) |
| **Does** | SandboxTemplate + network-policy YAML from roadmap §13; runner image buildable; document gVisor/non-root/no SA token posture. |
| **Dynamic verify** | `./scripts/verify_sandbox_gke.sh` → build image → (if `GKE_CONTEXT` set) apply template to a **dev** namespace → create one sandbox claim → exec `echo ok` or run Egaki install/build if demo pin ready → delete sandbox → assert destroyed |
| **Pass** | image builds always; cluster path PASS or `SKIP: GKE_CONTEXT unset` with instructions. Never report PASS without kubectl evidence |

---

### T-demo-baseline

| | |
|---|---|
| **Role** | `demo-engineer` |
| **Owns** | `demo/**`, `scripts/verify_demo_egaki.sh` |
| **Does** | Create `demo/fixtures/google-imagen4-deprecation.json` (roadmap §15.4). Create `demo/egaki/baseline.json` with real SHAs once fork exists. Add `expected-findings.yaml`, `verification-plan.yaml`, `demo-script.md` stubs filled with known facts. Adversarial fixtures from roadmap §16. Optionally vendor a shallow clone of the pinned Egaki SHA under `demo/egaki/checkout/` (gitignored) **or** document clone-by-SHA in the verify script. |
| **Dynamic verify** | `./scripts/verify_demo_egaki.sh`:  
| | 1. Confirm baseline SHA still contains Imagen 4 identifiers (`rg imagen-4.0-generate-001`).  
| | 2. `pnpm install --frozen-lockfile` in checkout.  
| | 3. `pnpm --dir cli build` and `pnpm --dir cli test` (or filter form).  
| | 4. Live: `egaki image ... -m gemini-3.1-flash-image -o demo/egaki/artifacts/verification.png` when `GOOGLE_API_KEY` set — assert file non-empty image. |
| **Pass** | steps 1–3 required for PASS; step 4 PASS or `SKIP: no API key`. Post-Aug-17: do **not** require Imagen 4 live success |

---

### T-skills

| | |
|---|---|
| **Role** | `demo-engineer` / `adk-agent-engineer` |
| **Owns** | `skills/google_imagen_migration/**` |
| **Does** | Skill Registry–shaped package: `SKILL.md`, `references/`, `checks/` with deterministic assertions (identifiers, forbidden merge language, etc.). |
| **Dynamic verify** | `uv run python skills/google_imagen_migration/checks/run_checks.py` against demo fixture |
| **Pass** | checks exit 0 on golden fixture; fail on adversarial “merge this yourself” note |

---

### T-infra-terraform

| | |
|---|---|
| **Role** | `cloud-infra-engineer` |
| **Owns** | `infra/terraform/**`, `scripts/verify_infra_terraform.sh` |
| **Does** | Modules/environments for `dev` and `demo`: project services enablement list from roadmap §21, Cloud Run stubs, GKE, Artifact Registry, Pub/Sub, Cloud SQL, Secret Manager, GCS. |
| **Dynamic verify** | `terraform -chdir=infra/terraform/environments/dev init` + `validate` + `plan` (apply only if `APPLY_INFRA=1`) |
| **Pass** | `validate` succeeds; plan exits 0. Apply is optional and human-gated |

---

### T-gemini-live

| | |
|---|---|
| **Role** | `qa-verifier` |
| **Owns** | `scripts/verify_gemini_live.sh`, `scripts/smoke_gemini_*.py` |
| **Depends** | T-packages-providers-google |
| **Does** | Cross-cutting live proofs required by hackathon rules. |
| **Dynamic verify** | | 
| | A. **Reasoning model:** call Gemini **3.5 Flash**, assert reply + model identity. |
| | B. **Image model:** call **`gemini-3.1-flash-image`** (or SDK path Egaki will use), write `demo/egaki/artifacts/gemini-image-smoke.png`, assert bytes look like an image (`file` / PIL). |
| **Pass** | both A and B exit 0 when credentials present; otherwise fail the task as blocked (do not mark setup complete) |

---

### T-github-app-live

| | |
|---|---|
| **Role** | `github-tools-engineer` |
| **Owns** | `scripts/verify_github_app_live.sh` only (uses `services/github_tools`) |
| **Does** | End-to-end read against `patchapi-demo/egaki-demo` (or configured fork): metadata + list tree at pinned SHA. |
| **Dynamic verify** | installation token path works; response SHA matches `demo/egaki/baseline.json` |
| **Pass** | PASS / `SKIP: fork or App not ready` |

---

### T-docs-scaffold

| | |
|---|---|
| **Role** | `docs-scribe` |
| **Owns** | `docs/*.md` (not `roadmap.md`), light README setup section |
| **Does** | Stub architecture/security/threat-model/data-model/agent-contracts/operations with links into roadmap sections. No fiction about deployed URLs. |
| **Dynamic verify** | `scripts/verify_docs.sh` — every `docs/*.md` exists, non-empty, contains a `Status:` line; relative links resolve |
| **Pass** | verifier exits 0 |

---

### T-qa-aggregate

| | |
|---|---|
| **Role** | `qa-verifier` |
| **Owns** | `demo/setup-report.md`, `scripts/verify_all.sh` |
| **Does** | Run every `scripts/verify_*.sh`, honor PASS/SKIP/FAIL, write human report. Compliance pass: no secrets in tree (`gitleaks` or `rg` for private key headers). |
| **Dynamic verify** | `./scripts/verify_all.sh` |
| **Pass** | zero FAIL; list SKIPs explicitly; MUST-have live Gemini checks not skipped if credentials were supposed to be present |

---

## 6. Dynamic verification matrix (quick view)

| Tree / concern | Command | What “works” means |
|---|---|---|
| Root Python | `./scripts/verify_root.sh` | uv sync + ruff + pytest collect |
| `apps/web` | `./scripts/verify_apps_web.sh` | npm build + HTTP 200 |
| Browser | `./scripts/verify_apps_web_browser.sh` | Playwright smoke + screenshot |
| Schemas | `./scripts/verify_packages_schemas.sh` | Pydantic round-trip |
| Gemini 3.5 Flash | `./scripts/verify_gemini_live.sh` | live text generation |
| Gemini 3.1 Flash Image | same script, image mode | non-empty PNG/JPEG on disk |
| ADK agents | `./scripts/verify_agents_adk.sh` | ADK smoke → ChangeManifest |
| Control API | `./scripts/verify_services_control_api.sh` | live `/healthz` |
| GitHub tools | `./scripts/verify_services_github_tools.sh` | allowlist + optional live read |
| Repo indexer | `./scripts/verify_services_repo_indexer.sh` | finds Imagen IDs in fixture |
| Postgres | `./scripts/verify_db.sh` | migrate/seed against Docker Postgres |
| Sandbox local | `./scripts/verify_sandbox_local.sh` | isolated build of testdata |
| Sandbox GKE | `./scripts/verify_sandbox_gke.sh` | image build; optional live claim |
| Egaki demo pin | `./scripts/verify_demo_egaki.sh` | SHA has Imagen 4; pnpm build/test; optional live image |
| Terraform | `./scripts/verify_infra_terraform.sh` | init/validate/plan |
| Docs | `./scripts/verify_docs.sh` | files + links |
| Aggregate | `./scripts/verify_all.sh` | full ledger |

---

## 7. Fleet dispatch plan (after you approve this doc)

Do **not** run until this file is reviewed.

Proposed batch: `.fleet/batches/setup-trees.json`

```text
Wave 0:  T-root-workspace
Wave 1:  T-apps-web | T-packages-schemas | T-db | T-demo-baseline | T-docs-scaffold | T-skills | T-infra-terraform
         then T-packages-providers-google | T-packages-remaining
Wave 2:  T-services-* | T-agents-adk | T-sandbox-local
Wave 3:  T-gemini-live | T-sandbox-gke | T-apps-web-browser | T-github-app-live
Wave 4:  T-qa-aggregate
```

Commands when approved:

```bash
./fleet doctor
./fleet run setup-trees --dry-run
./fleet run setup-trees
./fleet report setup-trees
./scripts/verify_all.sh
```

Each fleet task prompt will include: owned paths, forbidden paths, verify command, and “append to `demo/setup-ledger.ndjson`”.

---

## 8. Live API probe results (2026-08-11, project `patch-505223`)

> **Historical record.** This table is what the project looked like on
> 2026-08-11. Current deployment status lives in [`README.md`](./README.md) and
> [`docs/architecture.md`](./docs/architecture.md#google-platform-integration);
> the current provisioning summary is in
> [`docs/operations.md`](./docs/operations.md#cloud-provisioning). Do not read a
> row below as today's status. Two rows were also wrong about *why*, and are
> corrected in place.

Credentials: `.secrets/gcp-service-account.json` (Owner) + optional `.secrets/gemini_api_key.txt` (AI Studio). Both gitignored.

| Probe | Result | Notes |
|---|---|---|
| Enable core GCP APIs | **PASS** | Vertex/Agent Platform, GKE, Cloud Run, Pub/Sub, SQL Admin, Secret Manager, Artifact Registry, Scheduler, Model Armor API, etc. |
| Billing linked | **PASS** | `billingEnabled: true` |
| Vertex **`gemini-3.5-flash`** (`locations/global`) | **PASS** | Text generateContent → `{"ping":"pong"}`. Use **global**, not `us-central1`. |
| Vertex **`gemini-3.1-flash-image`** (`locations/global`) | **PASS** | IMAGE modality → PNG ~1.1MB under `.secrets/smoke-artifacts/` |
| Vertex `us-central1` for 3.5 / 3.1-image | **FAIL (404)** | Those model IDs are on **global** (and some Asia regions for 3.5) |
| AI Studio Generative Language API key | **BLOCKED (429)** | “prepayment credits are depleted” — Vertex path is fine without this |
| GCS / Pub/Sub / Secret Manager | **PASS** | Created smoke bucket/topic/secret |
| Cloud Run / GKE clusters | **empty** | APIs on; no services/clusters yet — **GKE live is in this setup batch** |
| Model Armor `us-central1` list | **FAIL (403)** | ~~Use `global` instead~~ — **wrong diagnosis.** The probe called the global host `modelarmor.googleapis.com` for a regional collection. Templates are served only from `modelarmor.LOCATION.rep.googleapis.com`; the global host carries floor settings and answers a template call with a permission error that reads like IAM and is not. Pinned in `packages/policy/config.py` as `ARMOR_ENDPOINT_HOST`. |
| Model Armor `global` list | **PASS** | Empty because floor settings, not templates, live there. Template `patchapi-untrusted-intake` now exists on the `us-central1` regional host. |
| Demo fork | **PASS** | Real fork [`amelia751/egaki`](https://github.com/amelia751/egaki) @ `c09e1a44200ff5e951746e013035e68aeb3a14b1` — Imagen 4 IDs present. Recorded in `demo/egaki/baseline.json` |
| Agent Runtime (`reasoningEngines`) | **PASS** | List API 200; empty then created instance. Not used for agent *execution* — PatchAPI runs its own Cloud Run worker pool. The one Agent Engine on this project is the Memory Bank. |
| Agent Registry API | **PASS** | `agentregistry.googleapis.com` enabled; `.../services` list 200 |
| Memory Bank | **PASS** | Created via Agent Platform SDK `client.agent_engines.create`. The engine is now configured through `PATCHAPI_MEMORY_BANK_ENGINE` / `PATCHAPI_MEMORY_BANK_LOCATION`; nothing reads `.secrets/memory_bank_name.txt`. |
| GitHub App | **deferred** | Per decision — later phase |
| GKE Agent Sandbox cluster | **not yet** | In scope for this setup batch (will provision) |

### Gemini Enterprise Agent Platform — enrollment status

**You do not need a separate “enroll” step for this project.** On `patch-505223` it already works:

1. `aiplatform.googleapis.com` enabled (this *is* the Agent Platform API in current docs)
2. `agentregistry.googleapis.com` enabled
3. SA has `roles/owner` + `roles/aiplatform.user` + `roles/aiplatform.memoryUser`
4. Live create: Memory Bank / Agent Engine resource  
   `projects/913371146929/locations/us-central1/reasoningEngines/6770363244553961472`

If a *new* GCP project ever needs setup, docs say:

1. Create/select project + enable billing  
2. Enable Agent Platform API:  
   https://console.cloud.google.com/apis/library/aiplatform.googleapis.com?project=PROJECT_ID  
   or `gcloud services enable aiplatform.googleapis.com agentregistry.googleapis.com`
3. Grant `roles/aiplatform.user` (and `roles/aiplatform.memoryUser` for Memory Bank R/W)
4. Optional console: https://console.cloud.google.com/vertex-ai?project=PROJECT_ID and https://console.cloud.google.com/agent-registry?project=PROJECT_ID  
5. Install SDK: `pip install 'google-cloud-aiplatform>=1.111.0'` (docs note `agentplatform.Client` as the newer entry point)

Reference: https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/start/cloud-environment

### What you may still need to do manually

1. **Delete empty shell repo** [`amelia751/egaki-demo`](https://github.com/amelia751/egaki-demo) — created by mistake; push blocked by repo rules. Needs `delete_repo` scope:  
   `gh auth refresh -h github.com -s delete_repo` then `gh repo delete amelia751/egaki-demo --yes`  
   Demo target is the real fork **`amelia751/egaki`**.
2. **Optional:** create GitHub org `patchapi-demo` in the web UI if you want the roadmap name; otherwise `amelia751/egaki` is fine for the hackathon.
3. **GitHub App** — later (as decided).
4. **AI Studio credits** — optional; Vertex path already works.
5. **GKE Agent Sandbox** — no extra enrollment found; we will create the cluster in this batch and install Agent Sandbox per https://docs.cloud.google.com/kubernetes-engine/docs/how-to/how-install-agent-sandbox

### Gemini CLI (local agent tooling)

Installed globally: `@google/gemini-cli` (`gemini` 0.55.1).

Project config lives in **`.gemini/`** (gitignored, like `.claude/` / `.fleet/`):

| File | Purpose |
|---|---|
| `.gemini/settings.json` | `security.auth.selectedType: vertex-ai`, model `gemini-3.5-flash` |
| `.gemini/.env` | `GOOGLE_CLOUD_PROJECT=patch-505223`, `GOOGLE_CLOUD_LOCATION=global`, SA path |
| `.gemini/GEMINI.md` | Workspace context for the CLI |

Tracked template: `.gemini.example/`. Smoke verified: `gemini -p "…OK…" -m gemini-3.5-flash` → `OK`.

### Locked decisions for setup fleet

| Topic | Decision |
|---|---|
| Dashboard | `apps/web/`, **npm** |
| GCP | `patch-505223`, regional `us-central1`, Gemini models on **`global`** |
| Demo fork | **`amelia751/egaki`** @ SHA above |
| GitHub App | **SKIP** this batch |
| GKE Agent Sandbox | **LIVE this batch** |
| Agent Platform | **Already working** — no enroll needed |

---

## 9. Open decisions (remaining)

1. ~~Demo fork~~ → **`amelia751/egaki`** pinned.
2. ~~GitHub App~~ → later / SKIP.
3. ~~GKE live~~ → **yes, this batch**.
4. ~~Browser E2E~~ → **Playwright now** (this batch).

---

## 10. Exit criterion for “setup complete”

Setup is complete when:

1. Every roadmap §6 tree exists with real installable code or templates.
2. `./scripts/verify_all.sh` reports **no FAIL**.
3. Gemini 3.5 Flash live smoke is **PASS** (credentials configured).
4. Gemini 3.1 Flash Image live smoke is **PASS** (credentials configured).
5. Egaki pinned baseline build/test is **PASS**.
6. Local sandbox runner is **PASS**.
7. GKE sandbox is **PASS** or an explicit, human-accepted **SKIP** with a dated follow-up batch.
8. `apps/web` HTTP + (if approved) browser smoke are **PASS**.
9. `demo/setup-report.md` lists every task outcome for the submission evidence trail.

---

*After you answer §8, the next step is to write `.fleet/batches/setup-trees.json` and dispatch the multi-agent fleet.*
