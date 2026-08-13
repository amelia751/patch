# Data model

**Status:** Console tenancy (2026-08-12) — Postgres currently stores the
dashboard's auth/import model. The eventual full schema — organizations, the
provider-usage inventory, runs, policy, PRs, audit — is [`schema.md`](../schema.md).
Workflow tables from [`roadmap.md` §10](../roadmap.md#10-state-architecture)
return as additive migrations against `projects` / `project_repositories`, not
as a parallel `repositories` catalog. Authoritative applied DDL:
[`db/migrations/`](../db/migrations/).

---

## Storage split

Four stores, each with one job. Using the wrong one is a correctness bug, not a
style preference.

| Store | Holds | Rule |
|---|---|---|
| **Postgres** (Cloud SQL; local Docker Postgres 16) | console tenancy (users, GitHub App connection, projects, imported repos, secret *names*) | passwords stay in Identity Platform; tokens stay at GitHub; secret values stay in Secret Manager |
| **Memory Bank** | institutional context across weeks | never the workflow database |
| **Cloud Storage** | evidence and artifacts | immutable, referenced by URI from Postgres |
| **Pub/Sub** | durable eventing between stages | messages carry IDs and URIs, never repository source |

## Postgres — console tenancy

Current table set (what the frontend actually writes):

```text
users
user_identities
github_connections
projects
project_repositories
workspaces
project_secrets
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

Workflow tables from roadmap §10.1 (`change_events`, `remediation_runs`,
`policy_decisions`, …) are not present. Add them later against `projects` /
`project_repositories` rather than inventing a parallel tenancy model.

### What does not go in Postgres

- Passwords and Identity Platform tokens
- GitHub App private keys and installation tokens
- Secret values / `.env` bodies
- Live GitHub repo catalogs (fetched on demand via `/api/github/repos`)

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

No Cloud SQL instance is provisioned. Local work uses Docker Postgres from
`db/docker-compose.yml`. See [`operations.md`](./operations.md).
