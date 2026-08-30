# Data model

**Status:** Revised 2026-08-30 — Postgres stores the dashboard's auth/import
model *and* the run state machine. The full intended schema is
[`schema.md`](../schema.md). Workflow tables from
[`roadmap.md` §10](../roadmap.md#10-state-architecture) landed as additive
migrations against `projects` / `project_repositories` rather than as a parallel
`repositories` catalog. Authoritative applied DDL:
[`db/migrations/`](../db/migrations/).

---

## Storage split

Four stores, each with one job. Using the wrong one is a correctness bug, not a
style preference.

| Store | Holds | Rule |
|---|---|---|
| **Postgres** (Cloud SQL; local Docker Postgres 16) | console tenancy (users, GitHub App connection, projects, imported repos, secret *names*) and the run state machine | passwords stay in Identity Platform; tokens stay at GitHub; secret values stay in Secret Manager |
| **Memory Bank** (Vertex AI Agent Engine) | institutional context across weeks | never the workflow database |
| **Cloud Storage** | evidence and artifacts | immutable, referenced by URI from Postgres |
| **Pub/Sub** | durable eventing between stages | messages carry IDs and URIs, never repository source |
| **Cloud Trace** (via the Telemetry API) | the run's reasoning chain, for reading | not durable audit; identifier-shaped attributes only, never document text |

Cloud Trace is a fifth store and is deliberately the weakest. It holds one trace
per run — `patchapi.run` plus the seven stage spans, with ADK's model and tool
spans nested underneath — which is what makes a run's reasoning chain readable.
It is not the audit record: attributes are restricted to the keys pinned in
`packages/observability/config.py` and to identifier-shaped values, so nothing
that would answer an audit question in prose can be stored there. The durable
audit trail is in Postgres.

## Postgres — console tenancy

Tenancy and provider-portal tables (what the frontend writes). The run-state
tables are listed under [Workflow state](#workflow-state); `db/migrations/` is
the complete set.

```text
users                      user_identities            github_connections
projects                   project_repositories       workspaces
project_secrets            project_notifications      gcp_connections
providers                  provider_connections       provider_services
provider_change_notes      project_provider_subscriptions
provider_usages            repo_index_state
```

| Table | Role |
|---|---|
| `users` | Dashboard profile. Identity Platform uid is optional until linked. No password column. |
| `user_identities` | GitHub / Google login. `User.github_id` and `github_username` come from here. |
| `github_connections` | GitHub App installation id. `github_app_installed` means this row exists. Tokens never stored. |
| `projects` | Named working set (`POST /api/projects/`). |
| `project_repositories` | Imported `owner/repo`. Live repo lists come from GitHub, not a cache of every visible repo. |
| `workspaces` | Clone URL, branch, optional subfolder from import-repo. |
| `project_secrets` | Secret name + ARN/resource pointer. Values live in Secret Manager. |

### Workflow state

The run state machine is here, not in Memory Bank and not in a trace
(constraint 7). Added by `0011` and `0014` (change corpus and impact) and `0018`
onward (runs):

```text
change_events              change_event_identifiers   change_event_snapshots
change_impacts             change_impact_findings     project_change_findings
remediation_runs           run_state_transitions      run_trace_events
policy_decisions           patch_attempts             verification_results
artifacts                  pull_requests              idempotency_keys
audit_events               remediation_workers
```

`idempotency_keys` is what makes every external action carry a key of
`run_id + action_type + base_sha`, and `remediation_workers` plus the lane,
lease, and heartbeat columns added by `0020`–`0023` are how the Cloud Run worker
pool claims a run and how anything outside a worker process tells a working
instance from a dead one.

`run_trace_events` is the durable, queryable record of what a run did. The Cloud
Trace export is a second, non-authoritative view of the same run, kept for
readability rather than audit — see the storage split above.

### What does not go in Postgres

- Passwords and Identity Platform tokens
- GitHub App private keys and installation tokens
- Secret values / `.env` bodies
- Live GitHub repo catalogs (fetched on demand via `/api/github/repos`)

## Memory Bank — institutional context

Vertex AI Agent Engine `6770363244553961472` in `us-central1`, reached over the
Agent Engine REST surface by `packages/memory/vertex.py`. `LocalMemoryBank` is
the offline fallback for tests and laptop runs, not the only implementation.

Two shapes live under one repository scope, kept apart because they are consumed
differently (`packages/memory/config.py`):

| Kind | Shape | Read by |
|---|---|---|
| `repository_profile` | one JSON fact behind a version marker: owning team, criticality, approval rules, previous migration decisions, known exceptions, canonical test commands, prohibited paths | recalled by exact scope |
| `previous_migration` | one prose sentence per migration outcome | retrieved by similarity, because a run months later asks "was something like this tried here before" and a JSON blob is not what that matches against |

Memory Bank informs judgment. It never determines run status, idempotency, or
audit truth. That is enforced by shape rather than convention: `agents/memory.py`
renders everything recalled into prose and drops the typed profile, so no
deterministic gate has a field to branch on. Recalled text is
injection-screened, bounded, and withheld entirely from the Verification Agent.
See [`threat-model.md`](./threat-model.md) T13.

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

Cloud SQL instance `patchapi-console` is provisioned and is where hosted runs
keep state; local work reaches it through the Auth Proxy
(`./scripts/run_cloud_sql_proxy.sh`) or uses Docker Postgres from
`db/docker-compose.yml` for offline verification. See
[`operations.md`](./operations.md).
