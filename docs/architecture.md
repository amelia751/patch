# Architecture

**Status:** Revised 2026-08-30. Design of record, not a description of running
infrastructure — nothing here is deployed unless the [Deployment
reality](#deployment-reality) or [Google platform
integration](#google-platform-integration) table says so. Authoritative source:
[`roadmap.md` §4](../roadmap.md#4-primary-architecture), which is a *plan* and
describes services PatchAPI turned out not to be able to use; where the roadmap
and this document disagree about what exists, this document wins.

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
| **Tools** | narrow GitHub capability service; Agent Registry as a catalog only | credential boundary |
| **Sandbox** | GKE Agent Sandbox running generated code | **untrusted execution**, default-deny network |

The Tools plane is a credential boundary because `services/github_tools/` is the
sole holder of the GitHub App key and exposes no operation that could merge or
reconfigure a repository. It is *not* a boundary enforced by Agent Gateway or
Agent Identity — see [Google platform
integration](#google-platform-integration) for why those are unavailable here.
Agent Registry is a catalog: every read in `packages/platform/registry.py` fails
soft and nothing in a run branches on the result, so a registry outage costs the
fleet its listing and never its run.

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
| `patchapi-agents` | Cloud Run service + `patchapi-remediate` job | ADK orchestrator + six specialist stages |
| `patchapi-api` | Cloud Run | webhooks, dashboard API, manual trigger, run-state queries. Never executes repository code |
| `patchapi-github-tools` | Cloud Run (private) | narrow GitHub capability surface; sole holder of GitHub App credentials |
| `patchapi-indexer` | Cloud Run push worker | API usage inventory; deterministic scanning, not an LLM agent |
| `patchapi-web` | Cloud Run | dashboard |
| sandbox runner | GKE Agent Sandbox | the only place generated code executes |

The roadmap §7.1 plans one Vertex AI Agent Runtime (`reasoningEngines`) instance
per agent. PatchAPI does not do that. The agent lane is PatchAPI's own Cloud Run
worker pool, which claims runs from Postgres by lane with a lease and a
heartbeat and resumes a paused run from an `agent_hold`
(`services/agent_runner/src/patchapi_agent_runner/remediation/worker.py`). That
is a deliberate choice, not an unfinished migration: the run state machine is
already authoritative in Postgres, and a lease plus a heartbeat is what lets
anything outside the process tell a working instance from a dead one. The
Agent Engine is used for Memory Bank and nothing else.

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

## Google platform integration

What PatchAPI actually calls, and what it does not. A surface that only appears
in a diagram is not a claim this project makes.

| Surface | State | Where it lives |
|---|---|---|
| **Agent Observability** (Telemetry API → Cloud Trace) | **wired.** OpenTelemetry spans export over OTLP to `telemetry.googleapis.com`. One trace per run: `patchapi.run` plus the seven stage spans, with ADK's `invocation` / `invoke_agent` / `call_llm` / `generate_content` / `execute_tool` spans nested underneath, because `stage_span` makes the stage span current across the stage's awaits. | `packages/observability/export.py`, `packages/observability/config.py`, `agents/observe.py` |
| **Memory Bank** (Vertex AI Agent Engine) | **wired.** Engine `6770363244553961472` in `us-central1`, over the Agent Engine REST surface with `google-auth`. `LocalMemoryBank` is the offline fallback, not the only implementation. | `packages/memory/vertex.py`, `agents/memory.py` |
| **Agent Registry** | **wired, catalog only.** Seven A2A agent cards plus one `McpServer` entry for the GitHub adapter. Card versions and skills are derived from the `agents/config.py` tool grants, so the catalog cannot drift from the implementation. The GitHub entry was created out of band: `scripts/register_agent_registry.py` publishes an `McpServer` only for `patchapi-mcp-tools`, and only when `PATCHAPI_MCP_URL` is set, which it is not. The Memory Bank engine is not a registry entry; it is discoverable on the Agent Engine surface. | `packages/platform/registry.py`, `agents/catalog.py`, `scripts/register_agent_registry.sh` |
| **Model Armor** | **configured, deliberately not authoritative.** Project floor settings enforce `INSPECT_ONLY` with logging, integrated inline with Vertex AI. Template `patchapi-untrusted-intake` serves the intake screen, opt-in per deployment. | `packages/policy/armor.py`, `packages/policy/config.py` |
| **Agent Identity** | **not available.** Per-agent SPIFFE identity is offered to Agent Runtime deployments, not to Cloud Run. | — |
| **Agent Gateway** | **not available.** Network-layer deny-by-tool-name is likewise unavailable to a Cloud Run deployment. | — |
| **Agent Runtime execution** | **not used, by choice.** See [Deployment units](#deployment-units). | — |
| **Skill Registry** | not wired. Migration skills are read from `skills/` in the repository. | `skills/` |

### What stands in for Agent Identity and Agent Gateway

These are PatchAPI's own controls. They are not the Google products and should
not be described with the product names.

- **Google-signed ID tokens between private services.** The agent lane fetches
  an ID token for the GitHub tool service's audience (`_service_identity` in
  `agents/tools/pr.py`) and the service is deployed private, so a caller has to
  be a named service account rather than anyone who learns the URL. That token
  is the only credential the agent side ever handles and it grants nothing
  beyond "you may ask the tool service".
- **Capabilities, never tokens.** The GitHub App private key stays inside
  `services/github_tools/`. An agent names a capability and receives a result.
- **A choke point with nothing dangerous on it.** Every GitHub write goes
  through that one service, and it implements no merge, administration, secret,
  or branch-protection operation. That is absence rather than enforcement, which
  is the stronger of the two: there is no code path to abuse.

What is genuinely lost by not having the Google services: there is no SPIFFE
attestation of *which* agent is calling, and no network-layer refusal of a tool
by name. `X-PatchAPI-Agent` is a header the tool service uses to scope grants,
and a header is not an attestation.

### Model Armor is defence in depth, not the gate

`packages/policy/injection.py` — NFKC folding, zero-width and bidi stripping,
then the tiered regex tables in `packages/policy/config.py` — plus
`packages/policy/command_allowlist.py` and the forbidden-path rules are the
authoritative fail-closed check. Model Armor is consulted only *after* that gate
has already allowed, so it can add a refusal and can never withdraw one.

The reason is not modesty about its accuracy: Google documents that Model
Armor's Vertex integration fails **open**, and a control that vanishes when it
breaks cannot be the control that says no. A run whose Armor verdict does not
arrive is marked `degraded` and proceeds cleared by the deterministic rules
alone, saying so in its audit record (`UntrustedTextScreening.degraded` and
`screened_by` in `packages/policy/armor.py`). Do not read a PatchAPI screening
as "Model Armor approved this" without checking `screened_by`.

## Deployment reality

Truthful status as of 2026-08-30. This table and the one above are the only
places in this document that describe what is actually running.

| Component | Reality today |
|---|---|
| GCP project, billing, core APIs | enabled and verified live |
| Gemini 3.5 Flash / 3.1 Flash Image on Vertex | verified live on the `global` endpoint |
| Cloud Run services | `patchapi-web`, `patchapi-api`, `patchapi-agents`, `patchapi-github-tools` (private), `patchapi-indexer`; jobs `patchapi-remediate`, `patchapi-refresh-releases` |
| Cloud SQL (Postgres 16) | instance `patchapi-console`; authoritative workflow state |
| GitHub App | installed; the live branch / commit / pull-request path works |
| Isolated patch execution | GKE cluster `patchapi-dev-agentsandbox` (`us-central1-a`) exists and is exercised by `./scripts/verify_sandbox_gke.sh`. The session backend is selected per run (`sandbox/session.py` `open_session`), so a run on the local temp workspace must not be described as sandboxed execution — check which backend the run used |
| Hosted URLs | see [`README.md`](../README.md) |

Design intent for the components above: [`operations.md`](./operations.md) for
provisioning and runbooks, [`data-model.md`](./data-model.md) for state,
[`threat-model.md`](./threat-model.md) for what each boundary defends against.
