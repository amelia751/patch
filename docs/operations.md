# Operations

**Status:** Scaffold (2026-08-11) — local development and verification only.
There is no deployed PatchAPI environment, so there are no production runbooks
to publish yet; the sections below marked *planned* describe intent from
[`roadmap.md` §21](../roadmap.md#21-infrastructure-provisioning). Setup plan of
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
```

The full command-to-meaning matrix is in
[`setup.md` §6](../setup.md#6-dynamic-verification-matrix-quick-view). Each run
appends one NDJSON line to `demo/setup-ledger.ndjson`:

```json
{"task":"T-docs-scaffold","status":"PASS","command":"./scripts/verify_docs.sh","at":"2026-08-11T00:00:00Z"}
```

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

Individual trees are landing through the setup batch, so a given command above
becomes available when its tree does. Run `./scripts/verify_all.sh` to see which
are live rather than assuming.

## Running a remediation locally

The Phase 1 vertical slice runs the full flow — provider fixture through
`ChangeManifest`, impact scan, policy, patch, isolated build and test, to a
`VerificationReport` — against a **local temp workspace**, not a cluster, and
stops at a patch artifact rather than a pull request. Details:
[`roadmap.md` §24](../roadmap.md#24-build-roadmap). Agent-by-agent behavior:
[`agent-contracts.md`](./agent-contracts.md).

## Isolation

Today: a local temp workspace. Patches are applied to a disposable copy, never
to the primary checkout. An unverified edit sitting in the working tree is not
a result.

Planned: GKE Agent Sandbox with gVisor, non-root execution, no mounted
service-account token, default-deny egress opened per phase, and short-lived
sandboxes destroyed after evidence collection
([`roadmap.md` §13](../roadmap.md#13-gke-agent-sandbox-design)). The cluster is
not provisioned. Do not describe the current local runner as sandboxed
execution.

## Cloud provisioning (planned)

Terraform under `infra/terraform/` covers `dev` and `demo` environments: service
enablement, Cloud Run, GKE, Artifact Registry, Pub/Sub, Cloud SQL, Secret
Manager, and GCS. The verifier runs `init`, `validate`, and `plan`; `apply` is
human-gated behind `APPLY_INFRA=1` and is never performed by an agent.

Confirmed live on the project as of 2026-08-11: billing, core API enablement,
Vertex text and image generation on `global`, GCS, Pub/Sub, Secret Manager,
Agent Runtime and Agent Registry API access, and one Memory Bank resource. Not
present: any Cloud Run service, any GKE cluster, any Cloud SQL instance, and any
Model Armor template. Full probe table:
[`setup.md` §8](../setup.md#8-live-api-probe-results-2026-08-11-project-patch-505223).

## Incident posture

PatchAPI has no automated remediation of its own failures, by design. When a run
fails it stops, persists the terminal state, retains evidence, and surfaces to a
human. The response to *any* uncertainty — missing provider evidence, ambiguous
migration, failing tests, unavailable live verification, verifier disagreement —
is no pull request. See [`roadmap.md` §22](../roadmap.md#22-failure-handling)
and [`security.md`](./security.md).

To stop all automation, revoke the GitHub App installation and disable the
provider polling schedule. Neither exists yet; when they do, this section gets
exact commands.
