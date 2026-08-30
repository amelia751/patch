# Operations

**Status:** Revised 2026-08-30 — local development and verification, plus the
checks that stand between a green checkout and a working deployment. Sections
marked *planned* describe intent from
[`roadmap.md` §21](../roadmap.md#21-infrastructure-provisioning). Hosted URLs
and the deployed service list: [`README.md`](../README.md). Setup plan of
record: [`setup.md`](../setup.md).

---

## Prerequisites

| Tool | Expected | Check |
|---|---|---|
| Python | 3.12+ | `python3 --version` |
| uv | recent | `uv --version` |
| Node | 20+ | `node --version` |
| npm | 10+ | `npm --version` |
| Docker | running | `docker info` |
| gcloud | authenticated | `gcloud auth list` |
| terraform | optional, for the infra tree | `terraform version` |
| GitHub CLI | for demo-fork checks | `gh auth status` |

## Configuration

```bash
cp .env.example .env      # then fill in local values
```

`.env` and `.secrets/` are gitignored. Never commit a credential, and never
paste one into a document, a prompt, an agent trace, or a log line.

Pinned values that must not be inlined at a call site:

| Variable | Value | Note |
|---|---|---|
| `PATCHAPI_REASONING_MODEL` | `gemini-3.5-flash` | agent reasoning |
| `PATCHAPI_IMAGE_MODEL` | `gemini-3.1-flash-image` | demo replacement model |
| `GCP_VERTEX_LOCATION` | `global` | both model IDs 404 on `us-central1` |
| `GCP_REGION` | `us-central1` | everything else |
| `DEMO_FORK` / `DEMO_FORK_SHA` | pinned fork + SHA | mirrored in `demo/egaki/baseline.json` |

Platform variables that decide whether a run reaches Google Cloud at all:

| Variable | Accepts | Unset means |
|---|---|---|
| `PATCHAPI_TRACE_EXPORTER` | `auto` \| `cloud` \| `console` \| `none` | `auto`, which resolves to Cloud Trace whenever `GCP_PROJECT` or `GOOGLE_CLOUD_PROJECT` is set and the OTLP exporter is installed, and to the console otherwise |
| `PATCHAPI_MEMORY_BANK_ENGINE` | Agent Engine id, or a full `projects/.../reasoningEngines/...` name | no Vertex Memory Bank; the lane falls back to `PATCHAPI_MEMORY_BANK_FILE` if set, and otherwise reports that it ran without institutional context |
| `PATCHAPI_MEMORY_BANK_LOCATION` | region | `us-central1` |
| `PATCHAPI_MODEL_ARMOR_ENABLED` | `1` / `true` | Model Armor is not consulted; screening is deterministic-only and says so |
| `PATCHAPI_REGISTRY_ENABLED` | `0` to disable | follows `GCP_PROJECT`; reads always fail soft |

`auto` is why the same image traces to Cloud Trace on Cloud Run and to stdout on
a laptop without a per-environment code path. The deploy workflow does not set
`PATCHAPI_TRACE_EXPORTER` and relies on that resolution.

Credentials come from `GOOGLE_APPLICATION_CREDENTIALS` pointing at a service
account key under `.secrets/`. The AI Studio API key path is optional and was
credit-blocked during the 2026-08-11 probe; the Vertex path works without it.

## Verification

Every tree ships a dynamic verifier under `scripts/`. A verifier executes code
or calls a live API — checking that files exist is not verification. Each exits
non-zero on failure and prints an explicit `SKIP:` with a reason when a required
credential or cluster is genuinely absent. A missing precondition is never
reported as a pass.

```bash
./scripts/verify_docs.sh      # documentation set (this tree)
./scripts/verify_all.sh       # every verifier, aggregated
./scripts/verify_all.sh --list  # the plan, running nothing
```

`verify_all.sh` carries a plan table of the trees it knows about, and it also
globs `scripts/verify_*.sh` and runs anything the table has not heard of, so a
new verifier cannot be silently dropped from the report. It appears as
`(unmapped)`.

The full command-to-meaning matrix is in
[`setup.md` §6](../setup.md#6-dynamic-verification-matrix-quick-view). Each run
appends one NDJSON line to `demo/setup-ledger.ndjson`:

```json
{"task":"T-docs-scaffold","status":"PASS","command":"./scripts/verify_docs.sh","at":"2026-08-11T00:00:00Z"}
```

### Checks that a green checkout does not cover

Two verifiers exist because passing in the repository is not the same as
working where the code actually runs.

```bash
./scripts/verify_agent_image_closure.sh                                  # image ⊇ imports
PATCHAPI_MODEL_ARMOR_LIVE=1 ./scripts/verify_policy_model_armor.sh       # live template
```

**`verify_agent_image_closure.sh`** answers whether the agent lane's container
image contains everything the agent lane imports. A checkout answers yes to
every import — `PYTHONPATH=.` makes the whole repository visible whether a
package is declared or copied or not — while the image is a subset chosen by the
`COPY` lines in `services/agent_runner/Dockerfile`, and nothing else before
deploy compares the two.

When they diverged, `packages/memory` and `packages/observability` were imported
by the orchestrator at module load and absent from the image. The deployed
worker started, passed its startup probe, claimed a run, and died on
`ModuleNotFoundError` while the console narrated that workers were on the air
and free. So the script stages a tree holding only what the Dockerfile copies,
resolves it the way the Dockerfile does, and imports the entry points from that
tree — missing files and undeclared dependencies both fail in seconds, without a
Docker daemon. Its staged list mirrors those `COPY` lines and fails if the two
drift, so adding a `COPY` means adding it to the script.

**`verify_policy_model_armor.sh`** calls the live Model Armor template. It skips
unless `PATCHAPI_MODEL_ARMOR_LIVE=1`, because the intake screen is opt-in and a
checkout with ambient Google credentials should not start billing an external
call from the unit suite. Note that templates are served only from the regional
host (`modelarmor.us-central1.rep.googleapis.com`); a call to the global
`modelarmor.googleapis.com` host, which carries floor settings, fails with a
permission error that reads like an IAM problem and is not.

## Local development loop

```bash
uv sync                       # Python workspace
uv run pytest -q              # PatchAPI's own tests
uv run ruff check .           # lint

npm --prefix apps/web ci      # dashboard deps
npm --prefix apps/web run dev # dashboard on :3000
```

Local Postgres for state work is owned by the `db/` tree:

```bash
docker compose -f db/docker-compose.yml up -d
docker compose -f db/docker-compose.yml down
```

Run `./scripts/verify_all.sh` to see what is live rather than assuming.

## Running a remediation locally

The vertical slice runs the full flow — provider fixture through
`ChangeManifest`, impact scan, policy, patch, isolated build and test, to a
`VerificationReport` — against a **local temp workspace** by default, and stops
at a patch artifact rather than a pull request unless
`PATCHAPI_GITHUB_TOOLS_URL` names a reachable tool service. Details:
[`roadmap.md` §24](../roadmap.md#24-build-roadmap). Agent-by-agent behavior:
[`agent-contracts.md`](./agent-contracts.md).

Traces from a local run go to stdout unless `GCP_PROJECT` is set, in which case
`PATCHAPI_TRACE_EXPORTER=auto` resolves to Cloud Trace and the run is readable
in the same place as a hosted one. Institutional memory follows
`PATCHAPI_MEMORY_BANK_ENGINE` the same way; with neither set, the run reports
that it had no institutional context rather than reporting an empty history.

## Isolation

Two backends, chosen per run by `open_session` in `sandbox/session.py`.

- **Local temp workspace.** Patches are applied to a disposable copy, never to
  the primary checkout. An unverified edit sitting in the working tree is not a
  result. This is not sandboxed execution and must not be described as such.
- **GKE Agent Sandbox** — gVisor, non-root, no mounted service-account token,
  default-deny egress opened per phase, short-lived sandboxes destroyed after
  evidence collection
  ([`roadmap.md` §13](../roadmap.md#13-gke-agent-sandbox-design)). Cluster
  `patchapi-dev-agentsandbox` in `us-central1-a` exists;
  `./scripts/verify_sandbox_gke.sh` builds the runner image and claims and
  destroys a live sandbox.

When reporting a run, say which backend it used. The posture claims above are
true of one of them.

## Cloud provisioning

Terraform under `infra/terraform/` covers `dev` and `demo` environments: service
enablement, Cloud Run, GKE, Artifact Registry, Pub/Sub, Cloud SQL, Secret
Manager, and GCS. The verifier runs `init`, `validate`, and `plan`; `apply` is
human-gated behind `APPLY_INFRA=1` and is never performed by an agent. The GKE,
Cloud SQL, and Cloud Run modules are gated off in `dev` because those were
bootstrapped by `./scripts/bootstrap_cloud_run.sh` and
`./scripts/bootstrap_cloud_sql.sh` rather than by Terraform. There is no
`hashicorp/google` resource for an Agent Registry Service, so
`./scripts/register_agent_registry.sh` creates those and Terraform owns only
the API enablement and IAM.

Confirmed live on project `patch-505223` as of 2026-08-30: billing, core API
enablement, Vertex text and image generation on `global`, GCS, Pub/Sub, Secret
Manager, Cloud SQL instance `patchapi-console`, the five Cloud Run services and
two jobs listed in [`README.md`](../README.md), GKE cluster
`patchapi-dev-agentsandbox`, Agent Registry (seven agent cards plus one
`McpServer` entry), Memory Bank engine `6770363244553961472`, Cloud Trace via
the Telemetry API, and one Model Armor template plus project floor settings. The
2026-08-11 probe table in
[`setup.md` §8](../setup.md#8-live-api-probe-results-2026-08-11-project-patch-505223)
is a historical record, not current status.

Not available on this architecture: Agent Identity and Agent Gateway, which do
not support Cloud Run deployments. See
[`architecture.md`](./architecture.md#google-platform-integration).

## Incident posture

PatchAPI has no automated remediation of its own failures, by design. When a run
fails it stops, persists the terminal state, retains evidence, and surfaces to a
human. The response to *any* uncertainty — missing provider evidence, ambiguous
migration, failing tests, unavailable live verification, verifier disagreement —
is no pull request. See [`roadmap.md` §22](../roadmap.md#22-failure-handling)
and [`security.md`](./security.md).

To stop all automation, revoke the GitHub App installation — that removes the
write path entirely — and scale the agent lane to zero. Provider polling on
Cloud Scheduler is not wired yet, so there is no schedule to disable.
