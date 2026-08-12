# Data model

**Status:** Scaffold (2026-08-11) — describes the intended storage split and
table set. Migrations under `db/` are the authoritative DDL once they land; this
document is a map, not a schema dump. Authoritative source:
[`roadmap.md` §10](../roadmap.md#10-state-architecture).

---

## Storage split

Four stores, each with one job. Using the wrong one is a correctness bug, not a
style preference.

| Store | Holds | Rule |
|---|---|---|
| **Postgres** (Cloud SQL; SQLite for early local work) | authoritative workflow state | a run being `TESTING` versus `PR_CREATED` must be deterministic and queryable |
| **Memory Bank** | institutional context across weeks | never the workflow database |
| **Cloud Storage** | evidence and artifacts | immutable, referenced by URI from Postgres |
| **Pub/Sub** | durable eventing between stages | messages carry IDs and URIs, never repository source |

## Postgres — authoritative state

Table set from [`roadmap.md` §10.1](../roadmap.md#10-state-architecture):

```text
organizations
repositories
api_usages
change_events
remediation_runs
run_state_transitions
policy_decisions
patch_attempts
verification_results
pull_requests
audit_events
```

Roles in the flow:

| Table | Role |
|---|---|
| `organizations`, `repositories` | tenancy and installation scope |
| `api_usages` | the API usage inventory — identifier, file path, kind, commit SHA. This is what makes impact analysis cheap enough to run per announcement |
| `change_events` | one row per normalized provider change, keyed by `change_id`, with source URIs and content hashes |
| `remediation_runs` | one row per (change, repository) run; carries `base_sha`, current state, and idempotency keys |
| `run_state_transitions` | append-only; written before and after every external side effect |
| `policy_decisions` | risk tier, allowed and forbidden actions, required checks, reason |
| `patch_attempts` | attempt number (capped at 2–3), diff hash, files touched |
| `verification_results` | independent verdict plus per-check outcomes and evidence URIs |
| `pull_requests` | PR number, URL, head SHA, the identity that opened it |
| `audit_events` | actor, action, resource, policy verdict, trace ID — written even when no model was involved |

### Run states

The state machine in
[`roadmap.md` §9](../roadmap.md#9-deterministic-orchestration) defines the
enumerated values:

```text
RECEIVED → SANITIZED → NORMALIZED → IMPACT_SCANNING
  ├─ UNAFFECTED                                   (terminal)
  └─ POLICY_EVALUATION
       ├─ HUMAN_REQUIRED                          (terminal)
       ├─ BLOCKED                                 (terminal)
       └─ PATCHING → BUILDING → TESTING → VERIFYING
              ↑          │          │        ├─ FAILED       (terminal)
              └─ RETRY_PATCH ───────┘        └─ PR_CREATING → PR_CREATED (terminal)
```

Four of the five terminal states — `UNAFFECTED`, `HUMAN_REQUIRED`, `BLOCKED`,
`FAILED` — are *not* a pull request. That ratio is the point: fail closed is the
default outcome, not the exception.

### Idempotency

Every external action is keyed:

```text
run_id + action_type + base_sha
```

Applied to PR creation, sandbox allocation, artifact writes, and Pub/Sub
consumption. A resumed process checks persisted state before repeating a side
effect.

## Memory Bank — institutional context

Per-repository profile recalled when a related change arrives weeks later:
owning team, criticality, provider dependencies, known API versions, approval
rules, previous migration decisions and why they were rejected, known
exceptions, canonical test commands, prohibited paths. Shape:
[`roadmap.md` §10.2](../roadmap.md#10-state-architecture).

Memory Bank informs judgment. It never determines run status, idempotency, or
audit truth.

## Cloud Storage — evidence

Raw provider snapshots, content hashes, unified diffs, build logs, test logs,
generated verification images, and final evidence bundles. Postgres rows point
at these URIs; the PR body cites them. Evidence is what makes an automated pull
request reviewable instead of merely plausible.

## Event topics

```text
provider-change-detected   change-normalized      repo-impact-requested
repo-affected              patch-requested        sandbox-complete
verification-requested     pr-requested
```

## Contracts on the wire

The typed payloads that move between agents — `ChangeManifest`, `ImpactReport`,
policy decision, `PatchPlan`, `VerificationReport` — are versioned Pydantic
models documented in [`agent-contracts.md`](./agent-contracts.md) and
implemented under `packages/schemas/`. Schema versions are pinned in
configuration, never inlined at a call site.

## Reality check

No Cloud SQL instance is provisioned and no Pub/Sub topics are wired as of
2026-08-11. Early local work uses SQLite or a Docker Postgres started from
`db/docker-compose.yml`. See [`operations.md`](./operations.md).
