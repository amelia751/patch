# Architecture

**Status:** Scaffold (2026-08-11) — design of record, not a description of
running infrastructure. Nothing in this document is deployed unless the
[Deployment reality](#deployment-reality) table says so. Authoritative source:
[`roadmap.md` §4](../roadmap.md#4-primary-architecture).

---

## What PatchAPI is

When an external API provider announces a change, PatchAPI finds the affected
code across an organization, generates a migration, verifies it in an isolated
environment, and opens an evidence-backed pull request for normal human review.

Then it stops. It does not merge, deploy, edit branch protection, rotate
secrets, or bypass CODEOWNERS and CI. That boundary is a product feature, not a
limitation — see [`security.md`](./security.md).

## Shape of the system

Five planes, each with a different trust level:

| Plane | Contains | Trust |
|---|---|---|
| **Intake** | provider watcher, content hashing, Model Armor screen, Change Intelligence Agent | processes **untrusted** provider text |
| **Fleet** | deterministic ADK orchestrator + six specialist agents | trusted, but never holds raw credentials |
| **State** | Postgres (authoritative), Memory Bank (institutional context), GCS (evidence) | trusted |
| **Tools** | narrow GitHub capability service, Agent Registry / Gateway / Identity | credential boundary |
| **Sandbox** | GKE Agent Sandbox running generated code | **untrusted execution**, default-deny network |

The full component diagram, including edges, lives in
[`roadmap.md` §4](../roadmap.md#4-primary-architecture). The one-page target
architecture is [`roadmap.md` §31](../roadmap.md#31-final-target-architecture-in-one-diagram).

## Flow of one remediation run

```text
provider change (untrusted text)
  → sanitize + hash + snapshot to evidence storage
  → Change Intelligence Agent      → ChangeManifest
  → Impact Agent (over the API usage inventory, not raw org-wide source)
                                   → ImpactReport
  → Policy & Risk Agent            → ALLOW | HUMAN_REQUIRED | BLOCKED
  → Patch Agent (in an isolated workspace, from a pinned base SHA)
                                   → PatchPlan + unified diff
  → build / tests / live replacement-API smoke test in the sandbox
  → Verification Agent (independent of the patch author)
                                   → VerificationReport, with veto power
  → PR Agent → GitHub tool service → branch + commit + pull request
  → human review
```

Agent-by-agent inputs, outputs, and guardrails:
[`agent-contracts.md`](./agent-contracts.md).

## Orchestration is deterministic

The critical path is an explicit state machine, not a supervisor model deciding
what happens next. States, transitions, and terminal outcomes are enumerated in
[`roadmap.md` §9](../roadmap.md#9-deterministic-orchestration); every transition
is persisted in Postgres before and after any external side effect, and every
external action carries an idempotency key of `run_id + action_type + base_sha`.

Agents supply judgment inside steps. They do not choose the steps.

## Deployment units

Source modules are granular; deployment units are deliberately few
([`roadmap.md` §7](../roadmap.md#7-deployment-units)):

| Unit | Runtime | Responsibility |
|---|---|---|
| `patchapi-fleet` | Agent Runtime | ADK orchestrator + six specialist agents |
| `patchapi-control-api` | Cloud Run | webhooks, dashboard API, manual trigger, run-state queries. Never executes repository code |
| `patchapi-github-tools` | Cloud Run | narrow GitHub capability surface; sole holder of GitHub App credentials |
| `patchapi-repo-indexer` | Cloud Run worker | API usage inventory; deterministic scanning, not an LLM agent |
| sandbox runner | GKE Agent Sandbox | the only place generated code executes |

## Repository layout

The monorepo tree is specified in
[`roadmap.md` §6](../roadmap.md#6-patchapi-monorepo-layout) and restated with
project conventions in [`CLAUDE.md`](../CLAUDE.md). Two deliberate deviations
from the roadmap, recorded in [`setup.md`](../setup.md):

- the dashboard lives at `apps/web/` and uses **npm**, not pnpm;
- `tests/` exists at the repository root for PatchAPI's own tests.

## Model and platform pins

| Concern | Pin | Where it lives |
|---|---|---|
| Agent reasoning | `gemini-3.5-flash` | `PATCHAPI_REASONING_MODEL` |
| Image replacement (demo target) | `gemini-3.1-flash-image` | `PATCHAPI_IMAGE_MODEL` |
| Vertex endpoint for both | `global` | `GCP_VERTEX_LOCATION` |
| Agent framework | Google ADK only | runtime dependency set |

Model IDs are configuration, never inlined at a call site. Regional endpoints
matter: both model IDs resolved on the `global` Vertex location and returned 404
on `us-central1` during the 2026-08-11 probe recorded in
[`setup.md` §8](../setup.md#8-live-api-probe-results-2026-08-11-project-patch-505223).

## Deployment reality

Truthful status as of 2026-08-11. This table is the only place in this document
that describes what is actually running.

| Component | Reality today |
|---|---|
| GCP project, billing, core APIs | enabled and verified live |
| Gemini 3.5 Flash / 3.1 Flash Image on Vertex | verified live on the `global` endpoint |
| Agent Runtime, Agent Registry, Memory Bank | API access verified; one Memory Bank resource created |
| Repository trees (`services/`, `agents/`, `packages/`, …) | being scaffolded by the setup batch; see [`setup.md`](../setup.md) |
| Isolated patch execution | **local temp workspace only**; GKE Agent Sandbox cluster not yet provisioned |
| GitHub App | **deferred** — no installation, no live PR path yet |
| Cloud Run services, Cloud SQL instance, Pub/Sub wiring | not deployed |
| Hosted URLs | none. There is no deployed PatchAPI endpoint to link to |

Design intent for the components above: [`operations.md`](./operations.md) for
provisioning and runbooks, [`data-model.md`](./data-model.md) for state,
[`threat-model.md`](./threat-model.md) for what each boundary defends against.
