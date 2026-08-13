# PatchAPI — eventual Postgres schema

**Version:** 2026-08-13
**Status:** Design. Authoritative DDL on disk is still only the console
tenancy in [`db/migrations/`](./db/migrations/). This file is the target the
next migrations should implement, not a description of what is already applied.

**Related:** [`roadmap.md`](./roadmap.md) §9–§11 (why), [`repo-indexer.md`](./repo-indexer.md)
(inventory tables), [`docs/data-model.md`](./docs/data-model.md) (storage split),
[`packages/schemas/`](./packages/schemas/) (wire contracts).

---

## 1. How to read this

The first schema in `roadmap.md` §10.1 assumed a greenfield product: `organizations`,
`repositories`, `change_events`, `remediation_runs`, … That set was discarded
when the console was rebuilt around GitHub import. What actually exists is a
tenancy model the dashboard already writes: users, a GitHub App connection,
projects, imported repos, workspaces, secret *names*, notifications.

The mistake to avoid is recreating a parallel `repositories` catalog next to
`project_repositories`. `packages/state/dashboard.py` still queries the discarded
names (`repositories`, `removed_at`, `owner_team`). Those queries are rewritten
against this schema; they are not a reason to bring the old tables back.

Four stores, one job each (`roadmap.md` §10):

| Store | Holds |
|---|---|
| **Postgres** | tenancy, inventory, runs, transitions, policy, PRs, audit |
| **Memory Bank** | institutional context across weeks (team, criticality, prior decisions) |
| **Cloud Storage** | diffs, logs, evidence bundles — Postgres stores URIs |
| **Pub/Sub** | IDs and URIs between stages, never source |

Passwords stay in Identity Platform. GitHub tokens stay at GitHub. Secret
values stay in Secret Manager. Live GitHub repo catalogs are fetched on demand.

---

## 2. What is already on disk (keep)

Applied migrations `0001`–`0006`. Do not recreate these tables.

```text
users
user_identities
github_connections          -- one App install per user today
projects                    -- team_id is a dangling uuid; see §4
project_repositories        -- UNIQUE (project_id, full_name)
workspaces                  -- optional workspace_path subfolder
project_secrets             -- name + ARN only
project_notifications
```

`project_status` already has `analyzing`, which is the console's coarse
"we are looking at this repo" flag. Fine-grained indexer progress lives on
`repo_index_state`, not by inventing a second project status.

---

## 3. Design rules

1. **A project is many repositories.** Indexing unit is `(full_name, branch)`,
   not the project. Findings have no `project_id`. See `repo-indexer.md` §3.1.
2. **A run is one repository in one project against one change.** A PR is a
   per-repository object. Frontend and backend of the same project are two runs.
3. **Do not duplicate GitHub.** `project_repositories` is the import. There is
   no `repositories` table. Owner team and criticality belong in Memory Bank.
4. **Rows are retired, not deleted.** Inventory and audit are evidence.
5. **Wire contracts are not tables.** `ChangeManifest`, `ImpactReport`,
   `PolicyDecision`, `PatchPlan`, `VerificationReport` stay versioned Pydantic
   in `packages/schemas/`. Postgres stores the durable projection a dashboard
   can query without hydrating a contract.
6. **Stop at the pull request.** `pull_requests.merged_by_patchapi` is a
   constant `false` column so a future migration cannot quietly enable merge.

---

## 4. Eventual map

```text
organizations ──────────── organization_members ── users
       │
       ├── organization_api_keys          -- BYOK pointers, not values
       ├── github_connections             -- install may move from user → org
       └── projects
              ├── project_repositories ── workspaces
              ├── project_secrets
              └── project_notifications

repo_index_state          -- keyed by (full_name, branch), shared, refcounted
provider_usages                -- facts about a commit; no project_id
project_provider_usages        -- VIEW: join + workspace_path filter

change_events             -- one provider change; not owned by a project
remediation_runs          -- (change_event, project_repository)
       ├── run_state_transitions
       ├── policy_decisions
       ├── patch_attempts
       │      └── verification_results
       ├── artifacts                      -- GCS URIs
       └── pull_requests                  -- at most one per run

audit_events              -- every meaningful action, model or not
idempotency_keys          -- run_id + action_type + base_sha
```

---

## 5. Enums to add

Existing (`0001`, `0006`): `user_type`, `identity_provider`, `project_status`,
`cloud_provider`, `repository_kind`, `secret_row_status`, `notification_kind`.

New, aligned with `packages/schemas/enums.py` and `run_state.py`:

```sql
CREATE TYPE org_role AS ENUM ('owner', 'admin', 'member');

CREATE TYPE index_status AS ENUM (
  'idle',        -- imported, not yet started
  'indexing',    -- the Codebase banner is visible
  'ready',
  'error'
);

CREATE TYPE detection_layer AS ENUM (
  'A_DETERMINISTIC',
  'B_STRUCTURAL',
  'C_SEMANTIC',
  'D_TYPE_PRECISE'
);

CREATE TYPE usage_kind AS ENUM (
  'runtime_source', 'configuration', 'test',
  'example', 'documentation_example', 'dead_code'
);

-- packages/schemas/run_state.py — the only legal vocabulary
CREATE TYPE run_state AS ENUM (
  'RECEIVED', 'SANITIZED', 'NORMALIZED', 'IMPACT_SCANNING',
  'UNAFFECTED', 'POLICY_EVALUATION', 'HUMAN_REQUIRED', 'BLOCKED',
  'PATCHING', 'BUILDING', 'RETRY_PATCH', 'TESTING', 'VERIFYING',
  'FAILED', 'PR_CREATING', 'PR_CREATED'
);

CREATE TYPE change_kind AS ENUM (
  'model_retirement', 'endpoint_removal', 'api_deprecation',
  'breaking_change', 'parameter_change', 'auth_change', 'behavior_change'
);

CREATE TYPE severity AS ENUM ('info', 'low', 'medium', 'high', 'critical');
CREATE TYPE risk_tier AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE policy_outcome AS ENUM ('allow', 'human_required', 'blocked');
CREATE TYPE check_outcome AS ENUM ('pass', 'fail', 'skip', 'inconclusive');
CREATE TYPE verdict AS ENUM ('pass', 'fail', 'inconclusive');
CREATE TYPE attempt_status AS ENUM ('running', 'succeeded', 'failed');
CREATE TYPE evidence_kind AS ENUM (
  'build_log', 'test_log', 'live_api_artifact',
  'diff', 'source_snapshot', 'sandbox_log'
);
CREATE TYPE pr_state AS ENUM ('open', 'closed', 'merged');
CREATE TYPE audit_outcome AS ENUM ('SUCCEEDED', 'DENIED', 'FAILED');
```

Legal run transitions live in Python (`assert_transition`), not in a trigger.
The database records what happened; the state machine decides what is allowed.

---

## 6. Console tenancy — additions

### 6.1 `organizations`

The dashboard already calls `/api/organizations` and `/api/organizations/:id/byok`.
There is no table. `projects.team_id` is the leftover hook.

This is the **console org** (who is a member, whose BYOK key is used). It is
not a GitHub organization and not a GCP organization. GitHub's account lives on
`github_connections.account_login`.

```sql
CREATE TABLE organizations (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text NOT NULL CHECK (length(btrim(name)) > 0),
  slug         text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
  created_by   uuid NOT NULL REFERENCES users (id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE organization_members (
  organization_id uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
  user_id         uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  role            org_role NOT NULL DEFAULT 'member',
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, user_id)
);

CREATE TABLE organization_api_keys (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
  display_name     text NOT NULL,
  -- Secret Manager resource name. No ciphertext column.
  secret_resource  text NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, display_name)
);
```

Then `ALTER TABLE projects DROP COLUMN team_id, ADD COLUMN organization_id uuid
REFERENCES organizations (id)`. Personal projects can keep `organization_id`
NULL and stay owned by `owner_id`.

`github_connections` stays per-user for the hackathon (`UNIQUE user_id`). An
org-scoped installation is a later additive column `organization_id`, not a
rewrite of import.

---

## 7. Indexer

Full rationale: [`repo-indexer.md`](./repo-indexer.md). Migration `0007`.

### 7.1 `provider_usages`

One row per identifier occurrence at a `(repository, branch)`. No `project_id`.

```sql
CREATE TABLE provider_usages (
  id               bigserial PRIMARY KEY,
  repository       text        NOT NULL CHECK (repository ~ '^[^/]+/[^/]+$'),
  branch           text        NOT NULL,
  provider         text        NOT NULL,
  identifier       text        NOT NULL,
  surface          text,
  file_path        text        NOT NULL,
  line_start       integer     NOT NULL CHECK (line_start >= 1),
  line_end         integer,
  usage_kind       usage_kind      NOT NULL,
  detection_layer  detection_layer NOT NULL,
  confidence       real        NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  excerpt          text        NOT NULL,
  observed_sha     text        NOT NULL,
  first_seen_at    timestamptz NOT NULL DEFAULT now(),
  last_seen_at     timestamptz NOT NULL DEFAULT now(),
  retired_at       timestamptz,
  UNIQUE (repository, branch, file_path, line_start, identifier, detection_layer)
);
```

`retired_at` is the name. Dashboard code that says `removed_at` is rewritten.

### 7.2 `repo_index_state`

Shared shard metadata **and** the Codebase tab's loading banner.

```sql
CREATE TABLE repo_index_state (
  repository         text         NOT NULL CHECK (repository ~ '^[^/]+/[^/]+$'),
  branch             text         NOT NULL,
  status             index_status NOT NULL DEFAULT 'idle',
  progress_percent   smallint     NOT NULL DEFAULT 0
                       CHECK (progress_percent BETWEEN 0 AND 100),
  indexed_sha        text,          -- NULL until the first successful pass
  shard_path         text,
  indexer_version    text         NOT NULL,
  scanner_version    text         NOT NULL,
  last_full_index    timestamptz,
  last_delta_index   timestamptz,
  file_count         integer      NOT NULL DEFAULT 0,
  reference_count    integer      NOT NULL DEFAULT 0 CHECK (reference_count >= 0),
  error_message      text,
  PRIMARY KEY (repository, branch)
);
```

`status = 'indexing'` is what makes the banner appear. `progress_percent` is
what fills the bar. No phase string — the UI is "Indexing codebase" plus `%`.

### 7.3 `project_provider_usages` (view)

Join plus `workspace_path` prefix filter. The only read path the dashboard and
the Impact Agent use for "usages in this project." Forgetting the filter is a
tenancy bug.

```sql
CREATE VIEW project_provider_usages AS
SELECT p.id AS project_id, pr.id AS project_repository_id, pr.kind, u.*
FROM provider_usages u
JOIN project_repositories pr ON pr.full_name = u.repository
JOIN projects p             ON p.id = pr.project_id
LEFT JOIN workspaces w      ON w.repository_id = pr.id
                           AND w.repo_branch = u.branch
WHERE u.retired_at IS NULL
  AND u.branch = COALESCE(w.repo_branch, pr.default_branch)
  AND (w.workspace_path IS NULL
       OR u.file_path LIKE w.workspace_path || '/%');
```

---

## 8. Provider changes and runs

### 8.1 `change_events`

A detected provider change. Not owned by a project — one Imagen retirement
fans out to every imported repo that uses those identifiers.

```sql
CREATE TABLE change_events (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id             text        NOT NULL,  -- ChangeManifest.change_id
  provider                text        NOT NULL,
  change_kind             change_kind NOT NULL,
  severity                severity    NOT NULL,
  title                   text        NOT NULL,
  source_urls             text[]      NOT NULL,
  source_sha256           text,                  -- hashed snapshot in GCS
  source_uri              text,                  -- GCS URI of the snapshot
  affected_identifiers    text[]      NOT NULL,
  -- Per-identifier mapping, not a single replacement. Roadmap §8.1 / fixture.
  replacements            jsonb       NOT NULL DEFAULT '[]',
  source_conflicts        jsonb       NOT NULL DEFAULT '[]',
  announced_at            date,
  effective_at            date,
  detected_at             timestamptz NOT NULL DEFAULT now(),
  manifest_uri            text                   -- versioned ChangeManifest JSON
);

CREATE INDEX change_events_external_id_detected_at
  ON change_events (external_id, detected_at DESC);
```

Re-polling the same page inserts another row with the same `external_id`.
The newest `detected_at` is current. Do not upsert away the previous detection;
the audit trail needs both.

`recommended_replacement` as a single text column is the old fixture shape.
Do not add it. `replacements` is `[{from, to, notes}]`.

### 8.2 `remediation_runs`

```sql
CREATE TABLE remediation_runs (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  change_event_id        uuid NOT NULL REFERENCES change_events (id),
  project_id             uuid NOT NULL REFERENCES projects (id),
  project_repository_id  uuid NOT NULL REFERENCES project_repositories (id),
  state                  run_state NOT NULL DEFAULT 'RECEIVED',
  base_sha               text        NOT NULL,
  trace_id               text,
  attempts_used          integer     NOT NULL DEFAULT 0,
  attempt_budget         integer     NOT NULL DEFAULT 3,
  failure_reason         text,
  started_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  ended_at               timestamptz,
  UNIQUE (change_event_id, project_repository_id)
);
```

The unique key is the fan-out unit: one change × one imported repo. Two
projects importing the same GitHub repo get two runs (two PRs, two reviews).

Terminal states: `UNAFFECTED`, `HUMAN_REQUIRED`, `BLOCKED`, `FAILED`,
`PR_CREATED`. There is no state after `PR_CREATED`.

### 8.3 `run_state_transitions`

Append-only. The current `remediation_runs.state` is the last `to_state`.

```sql
CREATE TABLE run_state_transitions (
  run_id       uuid NOT NULL REFERENCES remediation_runs (id),
  sequence     integer NOT NULL,
  from_state   run_state,
  to_state     run_state NOT NULL,
  actor        text NOT NULL,          -- orchestrator, or an agent id
  reason       text,
  occurred_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, sequence)
);
```

Persist the transition **before** the external side effect it authorizes
(`roadmap.md` §9).

### 8.4 `policy_decisions`

Deterministic engine output (`packages/schemas/policy_decision.py`). Latest
row per run is the one that counts; keep history.

```sql
CREATE TABLE policy_decisions (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id             uuid NOT NULL REFERENCES remediation_runs (id),
  decision           policy_outcome NOT NULL,
  risk               risk_tier NOT NULL,
  auto_patch         boolean NOT NULL,
  auto_pr            boolean NOT NULL,
  auto_merge         boolean NOT NULL DEFAULT false
                       CHECK (auto_merge = false),
  human_review_required boolean NOT NULL,
  forbidden_globs    text[] NOT NULL,
  required_checks    text[] NOT NULL,
  rule_ids           text[] NOT NULL,
  reason             text NOT NULL,
  policy_version     text NOT NULL,
  semantic_governance_verdict text,
  evaluated_at       timestamptz NOT NULL DEFAULT now()
);
```

### 8.5 `patch_attempts`

One row per outer-loop attempt. Inner-loop debug commands can be a JSONB
array of `{command, exit_code, log_uri}` — diagnostic, never evidence.

```sql
CREATE TABLE patch_attempts (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id             uuid NOT NULL REFERENCES remediation_runs (id),
  attempt_number     integer NOT NULL CHECK (attempt_number >= 1),
  status             attempt_status NOT NULL,
  patch_agent        text NOT NULL,
  patch_model        text NOT NULL,
  prompt_version     text NOT NULL,
  sandbox_ref        text,
  plan_uri           text,             -- PatchPlan JSON in GCS
  diff_uri           text,
  diff_sha256        text,
  files_changed      text[],
  build_exit_code    integer,          -- from the agent's own loop; not evidence
  test_exit_code     integer,
  debug_commands     jsonb NOT NULL DEFAULT '[]',
  failure_summary    text,
  started_at         timestamptz NOT NULL DEFAULT now(),
  ended_at           timestamptz,
  UNIQUE (run_id, attempt_number)
);
```

### 8.6 `verification_results`

Independent of the patch agent. `verifier_agent` must not equal `patch_agent`.

```sql
CREATE TABLE verification_results (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id             uuid NOT NULL REFERENCES remediation_runs (id),
  patch_attempt_id   uuid NOT NULL REFERENCES patch_attempts (id),
  verdict            verdict NOT NULL,
  verifier_agent     text NOT NULL,
  verifier_model     text NOT NULL,
  patch_agent        text NOT NULL,
  patch_model        text NOT NULL,
  build              check_outcome NOT NULL,
  tests              check_outcome NOT NULL,
  live_api           check_outcome,
  integrity_checks   jsonb NOT NULL DEFAULT '{}',
  identifier_mapping jsonb NOT NULL DEFAULT '[]',
  checks             jsonb NOT NULL,
  evidence_summary   text,
  report_uri         text,
  evaluated_at       timestamptz NOT NULL DEFAULT now()
);
```

### 8.7 `artifacts`

```sql
CREATE TABLE artifacts (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id             uuid NOT NULL REFERENCES remediation_runs (id),
  patch_attempt_id   uuid REFERENCES patch_attempts (id),
  kind               evidence_kind NOT NULL,
  uri                text NOT NULL,        -- gs://…
  content_sha256     text NOT NULL,
  size_bytes         bigint,
  media_type         text,
  created_at         timestamptz NOT NULL DEFAULT now()
);
```

Clean-run build/test logs (the ones the Verification Agent sees) are artifacts
on the attempt that produced the candidate diff. Agent-loop logs are
`debug_commands`, not this table.

### 8.8 `pull_requests`

At most one per run. PatchAPI opens it; humans merge it.

```sql
CREATE TABLE pull_requests (
  run_id              uuid PRIMARY KEY REFERENCES remediation_runs (id),
  number              integer NOT NULL,
  url                 text NOT NULL,
  title               text NOT NULL,
  head_branch         text NOT NULL,
  base_branch         text NOT NULL,
  head_sha            text NOT NULL,
  state               pr_state NOT NULL DEFAULT 'open',
  merged_by_patchapi  boolean NOT NULL DEFAULT false
                        CHECK (merged_by_patchapi = false),
  opened_at           timestamptz NOT NULL,
  observed_at         timestamptz NOT NULL DEFAULT now()
);
```

---

## 9. Audit and idempotency

### 9.1 `audit_events`

Every meaningful action, including Gateway denials and Model Armor
interceptions copied from Cloud Logging. The Fleet page still reads live
platform APIs for agents and SPIFFE IDs; this table is the product's own trail
so a run page can render without querying Cloud Logging.

```sql
CREATE TABLE audit_events (
  id                 bigserial PRIMARY KEY,
  run_id             uuid REFERENCES remediation_runs (id),
  project_id         uuid REFERENCES projects (id),
  actor              text NOT NULL,             -- agent id or 'orchestrator'
  actor_spiffe_id    text,
  action             text NOT NULL,
  target             text,
  repository         text,                      -- owner/repo, not an FK
  outcome            audit_outcome NOT NULL,
  reason             text,
  policy_verdict     text,
  semantic_governance_verdict text,
  trace_id           text,
  occurred_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX audit_events_run_id_idx ON audit_events (run_id);
CREATE INDEX audit_events_denied_idx ON audit_events (occurred_at DESC)
  WHERE outcome = 'DENIED';
```

No `repository_id` FK. The discarded `repositories` table is how the current
dashboard joins denials; join on `repository` text = `project_repositories.full_name`
if a project-scoped view is needed.

### 9.2 `idempotency_keys`

```sql
CREATE TABLE idempotency_keys (
  run_id        uuid NOT NULL REFERENCES remediation_runs (id),
  action_type   text NOT NULL,   -- open_pull_request, sandbox_allocate, …
  base_sha      text NOT NULL,
  result_ref    text,            -- PR number, sandbox id, artifact URI
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, action_type, base_sha)
);
```

---

## 10. What never lands in Postgres

| Thing | Where it lives |
|---|---|
| Passwords, ID tokens | Identity Platform |
| GitHub App private key, installation tokens | Secret Manager / GitHub Tools service |
| Secret values / `.env` bodies | Secret Manager (row stores the resource name) |
| Repository source, diffs, logs | GCS; URI + sha256 here |
| Agent reasoning traces | Cloud Trace / Agent Observability |
| Team, criticality, prior migration decisions | Memory Bank, scope `{"repo", "provider"}` |
| Registered agents, SPIFFE IDs, Gateway policy | Agent Registry / Runtime / Gateway APIs |
| Live GitHub repo catalog | GitHub API on demand |

---

## 11. Wire contracts vs tables

| Contract | Table it projects into |
|---|---|
| `ChangeManifest` | `change_events` (+ `manifest_uri` for the verbatim JSON) |
| `ImpactReport` | findings already in `provider_usages`; run state `IMPACT_SCANNING` → next |
| `PolicyDecision` | `policy_decisions` |
| `PatchPlan` | `patch_attempts.plan_uri` |
| `VerificationReport` | `verification_results` |

Schema versions stay in configuration, never inlined at a call site.

---

## 12. Dashboard query rewrite

`packages/state/dashboard.py` is written against the discarded schema. Map:

| Old | New |
|---|---|
| `repositories` | do not create. Impact page reads `project_repositories` ⨝ `repo_index_state` ⨝ `project_provider_usages` |
| `provider_usages.repository_id` | `(repository, branch)` text; project scope via the view |
| `provider_usages.removed_at` | `retired_at` |
| `repositories.indexed_sha` | `repo_index_state.indexed_sha` |
| `repositories.owner_team` / `criticality` | Memory Bank, not a column |
| `remediation_runs.repository_id` | `project_repository_id` |
| `change_events.recommended_replacement` | `replacements` jsonb |
| `audit_events.repository_id` | `audit_events.repository` text |

Organization impact (`roadmap.md` §17 page 2) is: for one `change_event`,
list `project_repositories` whose `project_provider_usages` match
`affected_identifiers`, with the latest run state per pair.

---

## 13. Indexer → Codebase banner

The banner in
`apps/web/src/components/interface/ops/codebase-tab/codebase-indexing-sign.tsx`
is forced on (`FORCE_SHOW_CODEBASE_INDEXING`). The schema above is what turns
it into truth.

```text
GET /api/projects/{id}/indexing
{
  "status": "indexing" | "ready" | "idle" | "error",
  "progress_percent": 47,
  "repositories": [
    {"full_name": "amelia751/egaki", "branch": "main",
     "status": "indexing", "progress_percent": 47}
  ]
}
```

Project-level `status` is `indexing` if any imported `(repo, branch)` is
`indexing`; `error` if any is `error` and none are still `indexing`; else
`ready` if all imported targets are `ready`; else `idle`.
`progress_percent` is the average over currently `indexing` rows, or 100
when `ready`.

The Codebase tab polls this. It renders `CodebaseIndexingSign` only when
status is `indexing`, and passes `progress={progress_percent}`. The preview
flag flips to `false`.

---

## 14. Suggested migration order

| # | File | Adds |
|---|---|---|
| 0007 | `provider_usages.sql` | enums `detection_layer`, `usage_kind`, `index_status`; `provider_usages`; `repo_index_state`; `project_provider_usages` |
| 0008 | `organizations.sql` | `organizations`, members, BYOK pointers; `projects.organization_id` |
| 0009 | `change_events.sql` | `change_kind`, `severity`; `change_events` |
| 0010 | `runs.sql` | `run_state` and the run family (`remediation_runs` … `pull_requests`) |
| 0011 | `audit.sql` | `audit_events`, `idempotency_keys` |

0007 is also task 1 of [`repo-indexer.md`](./repo-indexer.md). It does not
depend on organizations or runs. 0008 can wait until the org UI is more than
a client of a missing API. 0009–0011 are the workflow product
`packages/state/dashboard.py` already thinks exists.

---

## 15. Pub/Sub topics this schema implies

Existing closed set (`packages/events`, terraform): the run pipeline.

Add when the indexer worker exists, not before:

```text
repo-push
project-repo-added
project-repo-removed
index-updated
```

Payloads carry `repository`, `branch`, `project_id`, SHAs — never file
contents. See `roadmap.md` §10.4.
