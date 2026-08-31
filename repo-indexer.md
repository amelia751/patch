# PatchAPI — repository indexer implementation plan

**Version:** 2026-08-13
**Owner:** `services/repo_indexer`
**Roadmap section:** §7.4 (service), §11 (strategy)
**Eventual tables:** [`schema.md`](./schema.md) §7
**Status:** Layer A literal scanner exists and is tested, for one repository at a
time. Zoekt, ast-grep, the Postgres tables, multi-repository project scoping,
the webhook path, and the Codebase indexing banner wiring do not exist yet.

This document is the build. `roadmap.md` §11 is the reasoning behind it.

---

## 1. What this component is for

When a provider retires an API, PatchAPI must answer one question across an
entire organization, in seconds, with evidence:

> Which files, at which commits, reference the affected identifiers — and which
> of those references run in production?

That is a closed question with a checkable answer. It is not a semantic search
problem, and solving it with embeddings would trade an auditable file-and-line
citation for a similarity score. See §11.0 of the roadmap.

**Non-goals.** This service does not decide whether a usage is affected (Impact
Agent), does not write patches (Patch Agent), and does not talk to any model.
It produces candidates and evidence. Nothing here is allowed to be probabilistic.

---

## 2. Where the code is today

Already built, working, and tested — do not rewrite it:

| Path | What it does |
|---|---|
| `packages/repo_scan/scan.py` | Literal identifier walk over a checkout. Sorted traversal, so hit order is a property of the commit. |
| `packages/repo_scan/classify.py` | Path → `UsageKind` (runtime / config / test / example / docs / dead). Deterministic, pre-model. |
| `packages/repo_scan/config.py` | Extensions, skip dirs, size caps, `SCANNER_VERSION`. |
| `services/repo_indexer/.../index.py` | `build_inventory()` — full-tree and changed-paths entry points. |
| `services/repo_indexer/.../models.py` | `ApiUsageRecord`, `ApiUsageInventory`. Timestamp-free so two indexes of one commit serialize identically. |
| `services/repo_indexer/.../config.py` | Pinned watchlists, `INDEXER_VERSION`, `DETECTION_LAYER = "A_DETERMINISTIC"`. |

### Three gaps to close first

The first two are docstrings that reference things which do not exist. Fix them
before building on top, or the new work inherits the fiction.

1. `models.py` says rows are "shaped to the `provider_usages` table in
   `db/migrations/0003_api_usage_inventory.sql`". That file does not exist —
   `0003` is `github_connections.sql`. There is no `provider_usages` table anywhere.
2. `config.py` says `DETECTION_LAYER` "mirrors the `detection_layer` enum in
   `db/migrations/0001_types.sql`". That enum does not exist either.
3. `build_inventory()` takes a single `root` and a single `repository`, with no
   notion of a project, a branch, or a sibling repository. The console has
   supported many repositories per project since `0004_projects.sql`, so the
   scanner and the tenancy model currently disagree — see §3.1.

So: the inventory contract is real and tested, but nothing persists it and
nothing connects it to the projects that own the repositories. Tasks 1 and 2
below close both.

---

## 3. Target architecture

```text
GitHub push webhook
        │
        ▼
  control_api  ──── verify HMAC, enqueue ────►  Pub/Sub  ────►  repo_indexer
                                                                     │
                            ┌────────────────────────────────────────┤
                            ▼                                        ▼
                   git fetch + diff                          (first install)
                   base..head → paths                        full clone
                            │                                        │
                            ▼                                        ▼
                   Zoekt delta re-index  ◄──────────────────  Zoekt full index
                   ~0.13 s / push                             ~1 s / 484 files
                            │
                            ▼
                   Layer A: regex query over shards
                   `imagen-\d+\.\d+-(fast-|ultra-)?generate-\d+`
                            │
                            ▼  candidate files only
                   Layer B: ast-grep rules
                   call sites, imports, config keys
                            │
                            ▼
                   classify_path() → UsageKind
                            │
                            ▼
                   upsert provider_usages, retire deleted paths
                            │
                            ▼
                   Impact Agent reads rows, never the repo
```

Layer A is recall. Layer B is precision. The model is judgement. Each tier is
cheaper than the one after it and must not be skipped to save time.

### 3.1 Projects contain many repositories

The console tenancy model, already migrated, is not one-repo-per-project:

```text
projects
   └── project_repositories   UNIQUE (project_id, full_name)
         │                    kind: backend | frontend
         │                    default_branch
         └── workspaces       repo_branch
                              workspace_path   ← optional subfolder, NULL = root
                              environment
```

Three consequences the indexer has to be built around, not retrofitted with:

**The indexing unit is `(full_name, branch)`, not the project.** `UNIQUE` on
`project_repositories` is *per project*, so two projects can import the same
repository, and a repository is not owned by a project. Indexing per project
would build the same shard twice and produce two copies of every finding.

**Findings are facts about a commit; projects are views over them.** So
`provider_usages` is keyed by repository and branch with no `project_id` column, and
project attribution is a join at query time. Denormalizing the project onto the
row would mean N copies of one file-and-line, and they would drift.

**A project's view of a shared repository can be narrower than the repository.**
`workspaces.workspace_path` scopes a workspace to a subfolder. If project A
imported `acme/platform` at `packages/api` and project B imported the same repo
at `packages/web`, a finding in `packages/web/src/gen.ts` belongs to B only. The
project view is a join **plus a path-prefix filter**, and getting this wrong
puts another team's file in front of a reviewer.

```text
  one push to acme/platform
            │
            ▼
  index once  (full_name, branch)
            │
            ├──► project A   scope packages/api/**   → 0 findings, no run
            └──► project B   scope packages/web/**   → 3 findings, one run
```

#### Fan-out, and what stays per repository

One manifest against one project can affect several of its repositories. Each
affected repository gets **its own run and its own pull request** — a PR is a
per-repository object, and the frontend and backend of a project are reviewed by
different people on different CI. The project is the grouping the dashboard
shows; it is never the unit of remediation.

`project_repositories.kind` therefore selects the verification plan: a
`frontend` repo and a `backend` repo in one project do not share build or test
commands.

#### Access, sharing, and deletion

Sharing a shard between two projects is a tenancy boundary, so it needs rules
rather than an assumption:

- Every query is scoped to one project and re-checks that the project's GitHub
  installation still lists the repository. A shard is a cache of bytes someone
  was authorized to read *at index time*; authorization is checked at read time.
- A repository going private, or an installation being revoked, must retire the
  shard. Stale shards are the leak path here.
- Removing a repository from a project decrements a reference count. The shard
  is dropped only at zero — one project's cleanup must not blind another.

#### Branches

`project_repositories.default_branch` and `workspaces.repo_branch` can differ,
so one repository may be indexed at more than one branch. Index the distinct
branches actually imported, and **ignore pushes to refs nobody imported** — the
common case for a busy repository, and the cheapest possible early return.

---

## 4. Dependencies to install

### 4.1 Zoekt — Layer A index

Apache-2.0, Google-authored, Go. Operated standalone; **do not** pull in
Sourcegraph's `zoekt-sourcegraph-indexserver`, which assumes a Sourcegraph
instance.

```bash
go install github.com/sourcegraph/zoekt/cmd/zoekt-index@latest
go install github.com/sourcegraph/zoekt/cmd/zoekt-git-index@latest
go install github.com/sourcegraph/zoekt/cmd/zoekt-webserver@latest
```

Pin the commit in the Dockerfile, not `@latest`.

Why Zoekt rather than ripgrep: **regex over an index**. The watchlist needs
`imagen-\d+\.\d+-generate-\d+` to catch model IDs nobody enumerated, and it
needs the answer without re-reading the tree. Ripgrep gives the second only by
re-reading, and gives the first only per-invocation.

Measured, 484-file TypeScript repository:

| Operation | Time | Note |
|---|---|---|
| Cold index | 1.00 s | 4.3 MB shard, 3.0× overhead |
| No-change re-index | 0.24 s | shard reused |
| One-file delta | 0.13 s | the number that matters |

Shard overhead of ~3× means budgeting roughly 3 GB of disk per GB of indexed
source.

### 4.2 ast-grep — Layer B confirmation and rewrite

MIT, tree-sitter, vendored grammars.

```bash
# Rust binary, used by the service
cargo install ast-grep --locked
# or, for the sandbox where the Node toolchain already exists
npm install --save-dev @ast-grep/cli
```

Python bindings for in-process use:

```bash
uv add ast-grep-py
```

Why ast-grep rather than Semgrep: 1.27 s versus 10.70 s on the same tree with
equivalent rules, YAML rules that live in the repo, and it **rewrites** as well
as matches — the same rule file that finds a call site can propose the edit,
which the Patch Agent can apply deterministically instead of asking a model to
retype code it already understands.

Vendored grammars also sidestep the stale upstream `tree-sitter-typescript`
release, which is a real hazard for anything building grammars itself.

### 4.3 scip-typescript — Layer D, demo repository only

```bash
npm install -g @sourcegraph/scip-typescript
scip-typescript index --pnpm-workspaces
```

Gives true cross-package references in the Storygen pnpm workspace. **Not**
fleet-wide, for one reason that matters more than speed: when install or
type-check fails it emits a *silently incomplete* index. At scale, a degraded
index and "this repository is unaffected" look identical, and that is the one
failure mode this product cannot have.

Run it once, offline, for the demo repo. Treat a failed run as `HUMAN_REQUIRED`,
never as an empty result.

### 4.4 Nothing from Google Cloud

No first-party Google service indexes a git repository and exposes a query API.
The full rejection table is roadmap §11.4; the short version is that Gemini Code
Assist's index has no search method, and the Gemini Enterprise GitHub connector
would require read-write scopes that violate hard constraints #3 and #8.

Optional accelerator, only if Layer C needs more than snippets: **Gemini API
File Search** indexes `application/typescript`, returns `file_citation`, filters
on `custom_metadata`, and costs $0.15/1M tokens at index time with free storage
and query embedding. It requires writing the chunker. It never becomes Layer A.

---

## 5. Files to create

### 5.1 Database

**`db/migrations/0007_provider_usages.sql`** — new. Makes the existing
`models.py` docstring true.

```sql
CREATE TYPE detection_layer AS ENUM (
  'A_DETERMINISTIC',   -- Zoekt / literal walk
  'B_STRUCTURAL',      -- ast-grep
  'C_SEMANTIC',        -- Impact Agent
  'D_TYPE_PRECISE'     -- scip-typescript
);

CREATE TYPE usage_kind AS ENUM (
  'runtime_source', 'configuration', 'test',
  'example', 'documentation_example', 'dead_code'
);

CREATE TYPE index_status AS ENUM (
  'idle', 'indexing', 'ready', 'error'
);

-- Findings are facts about (repository, branch, commit). No project_id: one
-- file-and-line is one row however many projects import the repository, and
-- attribution is the join in `project_provider_usages` below.
CREATE TABLE provider_usages (
  id               BIGSERIAL PRIMARY KEY,
  repository       TEXT        NOT NULL CHECK (repository ~ '^[^/]+/[^/]+$'),
  branch           TEXT        NOT NULL,
  provider         TEXT        NOT NULL,
  identifier       TEXT        NOT NULL,
  surface          TEXT,
  file_path        TEXT        NOT NULL,
  line_start       INTEGER     NOT NULL CHECK (line_start >= 1),
  line_end         INTEGER,
  usage_kind       usage_kind      NOT NULL,
  detection_layer  detection_layer NOT NULL,
  confidence       REAL        NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  excerpt          TEXT        NOT NULL,
  observed_sha     TEXT        NOT NULL,
  first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  retired_at       TIMESTAMPTZ,
  UNIQUE (repository, branch, file_path, line_start, identifier, detection_layer)
);

CREATE INDEX provider_usages_lookup
  ON provider_usages (provider, identifier) WHERE retired_at IS NULL;
CREATE INDEX provider_usages_repo
  ON provider_usages (repository, branch) WHERE retired_at IS NULL;

-- One row per indexed (repository, branch). Shared by every project that
-- imported it; `reference_count` is why one project's cleanup cannot blind
-- another. `status` / `progress_percent` are what the Codebase tab banner
-- reads — see §7.6 and schema.md §7.2 / §13.
CREATE TABLE repo_index_state (
  repository         TEXT         NOT NULL CHECK (repository ~ '^[^/]+/[^/]+$'),
  branch             TEXT         NOT NULL,
  status             index_status NOT NULL DEFAULT 'idle',
  progress_percent   SMALLINT     NOT NULL DEFAULT 0
                       CHECK (progress_percent BETWEEN 0 AND 100),
  indexed_sha        TEXT,
  shard_path         TEXT,
  indexer_version    TEXT         NOT NULL,
  scanner_version    TEXT         NOT NULL,
  last_full_index    TIMESTAMPTZ,
  last_delta_index   TIMESTAMPTZ,
  file_count         INTEGER      NOT NULL DEFAULT 0,
  reference_count    INTEGER      NOT NULL DEFAULT 0 CHECK (reference_count >= 0),
  error_message      TEXT,
  PRIMARY KEY (repository, branch)
);
```

**The project view.** Attribution is a join against the existing tenancy tables
plus the `workspace_path` prefix filter from §3.1. It is a view rather than
hand-written SQL at each call site, because a call site that forgets the path
filter shows one team another team's files:

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
  -- NULL workspace_path means the whole repository is in scope.
  AND (w.workspace_path IS NULL
       OR u.file_path LIKE w.workspace_path || '/%');
```

Rows are **retired, never deleted** — `retired_at` set when a push removes the
line. Deleting evidence breaks the audit trail; a reviewer must be able to ask
what the inventory said last Tuesday.

`first_seen_at` / `last_seen_at` live here and not on `ApiUsageInventory`,
preserving the existing rule that the document is timestamp-free.

### 5.2 Zoekt integration

**`services/repo_indexer/src/patchapi_repo_indexer/zoekt/__init__.py`**

**`.../zoekt/shard.py`** — shard lifecycle.

```python
def index_repository(repo_path: Path, repository: str, branch: str) -> ShardInfo: ...
def delta_index(repo_path: Path, repository: str, branch: str,
                changed_paths: Sequence[str]) -> ShardInfo: ...
def shard_path_for(repository: str, branch: str) -> Path: ...
def acquire_shard(repository: str, branch: str) -> ShardInfo: ...   # refcount +1
def release_shard(repository: str, branch: str) -> None: ...        # -1, drop at 0
```

Wraps `zoekt-git-index`. One shard directory per **`(repository, branch)`** under
`ZOEKT_INDEX_DIR`, named by a hash of `full_name@branch` so a repository called
`../../etc` cannot escape and two projects importing the same repository share
one shard (§3.1).

`acquire_shard` / `release_shard` carry the reference count. Nothing else may
call `drop_shard` directly — a project removing a repository is a release, not a
delete.

**`.../zoekt/query.py`** — query client.

```python
def search(pattern: str, *, repository: str | None = None, branch: str | None = None,
           regex: bool = True, max_results: int = 1000) -> list[ZoektMatch]: ...
def search_shards(pattern: str, shards: Sequence[ShardRef]) -> list[ZoektMatch]: ...
```

Talks to `zoekt-webserver` over its JSON API on localhost. Every query is scoped
to an explicit shard set. `search_shards` takes the shards a caller is entitled
to rather than filtering results afterwards: an unscoped query that is filtered
late is one forgotten `WHERE` away from crossing a tenant boundary.

**`.../zoekt/patterns.py`** — regex per provider, versioned alongside the
watchlist. The whole point of Layer A being an index and not a `grep`:

```python
GOOGLE_IMAGEN_FAMILY = r"imagen-\d+\.\d+-(fast-|ultra-)?generate-\d+"
GOOGLE_IMAGEN_PREVIEW = r"imagen-[\d.]+-[\w-]*preview[\w-]*"
```

The preview pattern exists because the retired `-preview` identifier is its own
finding in `demo/storygen/expected-findings.yaml`, not a variant of the GA one.

### 5.3 ast-grep integration

**`.../astgrep/__init__.py`**

**`.../astgrep/runner.py`**

```python
def scan_files(rule_dir: Path, files: Sequence[Path],
               root: Path) -> list[StructuralMatch]: ...
def rewrite(rule: Path, files: Sequence[Path], root: Path) -> str: ...  # unified diff
```

Invokes `ast-grep scan --json=stream` and parses per-line JSON, so a large
result set streams instead of buffering. `rewrite` returns a diff and never
writes to disk — applying is the sandbox's job, per hard constraint #5.

**`.../rules/google-imagen-call-site.yml`**

```yaml
id: google-imagen-call-site
language: typescript
severity: info
message: Imagen model identifier in a generation call
rule:
  any:
    - pattern: $CLIENT.models.generateImages({ model: $MODEL, $$$ })
    - pattern: $CLIENT.getGenerativeModel({ model: $MODEL, $$$ })
constraints:
  MODEL:
    regex: 'imagen-\d+\.\d+'
```

**`.../rules/google-imagen-config.yml`** — the same identifier in JSON/YAML/env
configuration, which `classify_path` labels `configuration` and which is
runtime-affecting even though it is not code.

**`.../rules/README.md`** — how to add a provider rule and how it is tested.

### 5.4 Persistence

**`.../store.py`**

```python
def persist_inventory(conn, inventory: ApiUsageInventory) -> PersistResult: ...
def retire_paths(conn, repository: str, branch: str,
                 paths: Sequence[str], sha: str) -> int: ...
def load_state(conn, repository: str, branch: str) -> RepoIndexState | None: ...
def record_state(conn, state: RepoIndexState) -> None: ...

# Tenancy (§3.1). Nothing outside this module joins projects to findings.
def indexable_targets(conn) -> list[IndexTarget]: ...
    # distinct (full_name, branch) across all project_repositories + workspaces
def projects_for(conn, repository: str, branch: str) -> list[ProjectScope]: ...
    # (project_id, project_repository_id, kind, path_prefix | None)
def usages_for_project(conn, project_id: UUID,
                       identifiers: Sequence[str]) -> list[ApiUsageRecord]: ...
    # reads the project_provider_usages view; never provider_usages directly

def set_index_progress(conn, repository: str, branch: str, *,
                       status: str, progress_percent: int,
                       error_message: str | None = None) -> None: ...
def indexing_for_project(conn, project_id: UUID) -> ProjectIndexingStatus: ...
    # aggregates repo_index_state across the project's imported (repo, branch)
    # pairs. This is the Codebase tab banner (§7.6).
```

`persist_inventory` upserts on the unique key and bumps `last_seen_at`. It is
idempotent by construction: replaying the same push produces the same rows,
which is what lets Pub/Sub deliver at-least-once without corrupting the
inventory. Because rows carry no `project_id`, a repository shared by two
projects is still one set of rows.

`usages_for_project` is the only read path the dashboard and the Impact Agent
use. It goes through the view, so the `workspace_path` filter cannot be
forgotten.

### 5.5 Git access

**`.../git.py`**

```python
def ensure_checkout(repository: str, branch: str, sha: str) -> Path: ...
def changed_paths(repo_path: Path, base_sha: str, head_sha: str) -> list[str]: ...
def prune_checkouts(max_bytes: int) -> None: ...
```

One bare mirror clone per **repository** under `INDEXER_WORKDIR` — branches are
refs in the same mirror, so indexing two branches costs one clone — fetched
incrementally.

Clone credentials come from the GitHub tool service as a short-lived
installation token; this service holds no GitHub App private key (hard
constraint #8). The token is resolved from the installation backing the project
that requested the index, and access is re-checked rather than assumed from the
shard's existence (§3.1).

### 5.6 Service entry point

**`.../worker.py`** — Pub/Sub subscriber.

```python
def handle_repo_added(event: ProjectRepoAdded) -> None: ...      # acquire + full index
def handle_repo_removed(event: ProjectRepoRemoved) -> None: ...  # release shard
def handle_push(event: RepoPushEvent) -> None: ...               # delta, then fan out
def handle_manifest(event: ChangeManifestReady) -> None: ...     # fleet query
```

`handle_repo_added` fires per `project_repositories` row, not per project. If the
shard for that `(repository, branch)` already exists it only takes a reference,
so importing an already-indexed repository into a second project is close to
free.

`handle_manifest` is the one that makes the scalability claim true: a new change
manifest triggers **no cloning at all**. It queries existing shards for the
manifest's identifiers and returns affected `(project, repository)` pairs from
the index.

**`services/repo_indexer/Dockerfile`** — extend to carry `zoekt-index`,
`zoekt-git-index`, `zoekt-webserver`, `ast-grep`, and `git`; multi-stage from
`golang:1.23` and `rust:1.83` into the Python runtime.

---

## 6. Files to modify

| File | Change |
|---|---|
| `services/repo_indexer/.../index.py` | Add `build_inventory_zoekt()` alongside the existing function. Same `ApiUsageInventory` return. Do not touch the working literal path. |
| `services/repo_indexer/.../config.py` | Add `ZOEKT_INDEX_DIR`, `ZOEKT_WEBSERVER_URL`, `ASTGREP_RULE_DIR`, `INDEXER_WORKDIR`, `LAYER_B_CONFIDENCE = 0.9`, `INDEX_BACKEND` (`zoekt` \| `literal`). Bump `INDEXER_VERSION` to `1.1.0`. |
| `services/repo_indexer/.../models.py` | Widen `detection_layer` to the four-value literal union. Add `branch` to `ApiUsageInventory`. **Delete the docstring reference to `0003_api_usage_inventory.sql`** and point at `0007_provider_usages.sql`. |
| `services/repo_indexer/.../errors.py` | Add `ZoektUnavailableError`, `ShardCorruptError`, `AstGrepRuleError`, `RepositoryAccessRevokedError`. |
| `services/repo_indexer/pyproject.toml` | Add `ast-grep-py`, `httpx`, `asyncpg`. |
| `packages/repo_scan/README.md` | State that this is now the fallback backend, and when it is selected. |
| `packages/state/projects.py` | `add_repository` / `import_repo_workspace` publish `ProjectRepoAdded`; repository removal publishes `ProjectRepoRemoved`. Today they only write rows, so an imported repo is never indexed. |
| `services/control_api/` | Push webhook route: verify HMAC, publish `repo.push`. The API must not scan inline — a large monorepo push would blow the webhook timeout. |
| `packages/events/` | `RepoPushEvent`, `ProjectRepoAdded`, `ProjectRepoRemoved`, `IndexUpdated` — all carrying `repository` **and** `branch`. |
| `apps/web` project view | Read `project_provider_usages`, grouped by repository, with `kind` shown. A project with three repos is three groups, not one list. |
| `apps/web/.../codebase-indexing-sign.tsx` | Flip `FORCE_SHOW_CODEBASE_INDEXING` to `false`. `withCodebaseIndexingSign` takes live `{status, progress_percent}` instead of always wrapping. |
| `apps/web/.../codebase-tab.tsx` | Read live `{status, progress_percent}` from the project console SSE stream; hide the banner unless `status === "indexing"`. Poll `GET /indexing` only if the stream drops. |
| `packages/state/project_routes.py` | Add `GET /api/projects/{id}/indexing` reading `indexing_for_project`. |
| `.env.example` | The new variables above. |
| `docs/data-model.md` | `provider_usages`, `repo_index_state`, and the `project_provider_usages` view alongside the existing tenancy tables. |
| `schema.md` | Keep §7 in step with the migration that actually lands. |
| `docs/architecture.md` | Layered detection, the fallback story, and the shared-shard model. |
| `infra/terraform/` | Persistent disk for shards, Pub/Sub topic and subscription. |

---

## 7. Wiring

### 7.1 Backend selection, fail-soft

```python
# config.py
INDEX_BACKEND: Final[str] = os.getenv("PATCHAPI_INDEX_BACKEND", "zoekt")
```

```python
# index.py
def build_inventory(*, root, repository, observed_sha, provider=DEFAULT_PROVIDER,
                    identifiers=None, changed_paths=None) -> ApiUsageInventory:
    if INDEX_BACKEND == "zoekt":
        try:
            return build_inventory_zoekt(...)
        except (ZoektUnavailableError, ShardCorruptError):
            # Degrade to the literal walk rather than report a repository as
            # clean because the index was not reachable. Slower and lower
            # recall is a tolerable answer; a false negative is not.
            log.warning("zoekt unavailable, falling back to literal scan",
                        repository=repository)
    return build_inventory_literal(...)
```

This is the roadmap §11.6 property, and it is worth demonstrating: kill
`zoekt-webserver` mid-demo and the pipeline keeps producing findings.

### 7.2 Push path

```text
GitHub  ──push──►  control_api /webhooks/github
                        │ verify X-Hub-Signature-256
                        │ 202 immediately
                        ▼
                   Pub/Sub  topic: patchapi.repo.push
                        ▼
                   repo_indexer.worker.handle_push
                        │ ref imported by anyone?  no → drop, done
                        │ git fetch; diff base..head
                        │ zoekt delta re-index      (~0.13 s)   ← once
                        │ Layer A regex query
                        │ Layer B ast-grep on candidates
                        │ persist_inventory + retire_paths
                        ▼
                   projects_for(repository, branch)              ← fan out
                        ▼
                   Pub/Sub  topic: patchapi.index.updated  × N projects
```

Index once, notify many. The early return on an unimported ref matters more than
it looks: most pushes to a busy repository are to branches no project imported,
and dropping them before the fetch is the difference between a webhook that
keeps up and one that queues.

### 7.3 Manifest path — the scalability claim

```python
def handle_manifest(event: ChangeManifestReady) -> None:
    patterns = patterns_for(event.provider, event.affected_identifiers)
    # One query across every shard. No clone, no fetch, no per-project scan.
    matches = zoekt.search_shards(patterns, shards=all_indexed_shards())
    for repository, branch in dedupe(matches):
        # A repository shared by several projects is searched once and
        # remediated per project: a PR is a per-repository object, and two
        # projects reviewing the same repo are two separate reviews.
        for scope in store.projects_for(conn, repository, branch):
            if not scope.covers(matches[repository, branch]):
                continue          # outside this project's workspace_path
            publish(ImpactAnalysisRequested(
                project_id=scope.project_id,
                project_repository_id=scope.project_repository_id,
                repository=repository, branch=branch,
                manifest_id=event.manifest_id))
```

Answering "which of 2,000 repositories use `imagen-4.0-generate-001`" is an
index query, not 2,000 clones. That sentence is the §11 thesis; this function is
where it is either true or not.

Note the unit of the emitted event: `(project, repository)`. A project with a
frontend and a backend both using the identifier produces two impact analyses,
two runs, and two pull requests, grouped under one project in the dashboard.

### 7.4 What the Impact Agent receives

Rows plus bounded excerpts — never a repository, never a file. Excerpts are
already capped at 240 characters by `MAX_EXCERPT_CHARS`. Layer A hits carry
confidence 1.0 (the bytes are there or they are not); Layer B carries 0.9;
uncertainty belongs to the tiers that reason.

Rows come from `usages_for_project`, so the agent sees one project's scope and
one repository at a time. It never receives rows from a sibling repository in
the same project unless the orchestrator asked for that repository — the
verification plan and the diff are per repository, so a mixed set would only
invite a cross-repo patch that no single PR can carry.

### 7.5 Sandbox reuse

The sandbox image carries the same `ast-grep` binary and the same rule files, so
a rule that identified a call site can propose the rewrite. The Patch Agent
applies deterministic rewrites where a rule covers the case and reserves model
generation for what the rules cannot express. Cheaper, and far easier for the
Verification Agent to check.

### 7.6 Codebase tab — indexing banner

The banner already exists, forced on for design review:

`apps/web/src/components/interface/ops/codebase-tab/codebase-indexing-sign.tsx`

Copy is **Indexing codebase** plus a `%` and a thin progress bar. No phase
labels. `FORCE_SHOW_CODEBASE_INDEXING = true` is preview-only.

Wire it like this:

```text
repo_indexer.worker
    │ set_index_progress(repo, branch, status=indexing, 0)
    │ … fetch, shard, scan …
    │ set_index_progress(..., progress_percent=n)   -- periodically
    │ record_state(..., status=ready, 100)
    │ pg_notify(patchapi_console)  -- one wake per importing project
    ▼
GET /api/projects/{id}/events      ← SSE snapshot, then indexing events
GET /api/projects/{id}/indexing    ← poll fallback if the stream drops
    ▼
status === "indexing"  →  <CodebaseIndexingSign progress={n} />
otherwise              →  banner hidden
```

Project-level rollup (also in [`schema.md`](./schema.md) §13):

| If any imported `(repo, branch)` is | Project `status` |
|---|---|
| `indexing` | `indexing` |
| `error` and none `indexing` | `error` |
| all `ready` | `ready` |
| else | `idle` |

`progress_percent` is the average over currently `indexing` rows, or 100 when
`ready`. A project with two repos, one indexing at 20% and one at 80%, shows
50%. Do not invent a second `project_status` for this — `projects.status =
analyzing` can stay as the coarse console flag; the banner reads
`repo_index_state`.

When this lands:

1. Flip `FORCE_SHOW_CODEBASE_INDEXING` to `false`.
2. Change `withCodebaseIndexingSign` to take the live status (or stop using the
   wrapper and render the sign from `CodebaseTab` directly).
3. Pass `progress={data.progress_percent}` so the preview loop stops.

Until the endpoint exists, leave the force-show flag on so the banner can still
be reviewed.

---

## 8. Build order

| # | Task | Depends on | Output |
|---|---|---|---|
| 1 | `0007_provider_usages.sql` + `project_provider_usages` view | — | Existing inventories persist. Closes the phantom-migration gap. Includes `index_status` + `progress_percent` on `repo_index_state`. |
| 2 | `store.py`, including `indexable_targets` / `projects_for` / `indexing_for_project` | 1 | Multi-repo projects resolve to a deduplicated `(repo, branch)` work list. Banner has a read model. |
| 3 | `git.py` mirror clones and diffing | 2 | Changed paths from a real push. |
| 4 | Zoekt in the Dockerfile, `zoekt/shard.py` with refcounts | 3 | Shard built once, shared by projects. |
| 5 | `zoekt/query.py` + `patterns.py` | 4 | Regex recall beats the literal watchlist on the Storygen fixture. |
| 6 | `build_inventory_zoekt()` + fallback | 5 | Backend swap with unchanged output contract. |
| 7 | ast-grep rules + `astgrep/runner.py` | 6 | Layer B precision, prose hits dropped. |
| 8 | `ProjectRepoAdded` / `Removed` from `packages/state/projects.py` | 2, 4 | Importing a repo indexes it; removing it releases the shard. Worker writes `set_index_progress`. |
| 9 | `GET /api/projects/{id}/indexing` + flip the Codebase banner off preview | 2, 8 | Banner shows only while `status === "indexing"`, with a real `%`. |
| 10 | Webhook → Pub/Sub → `worker.py` with project fan-out | 1–8 | Push updates the inventory and notifies every affected project. |
| 11 | `handle_manifest` fleet query | 10 | Manifest to affected `(project, repo)` pairs, no cloning. |
| 12 | scip-typescript, demo repo, offline | 7 | Cross-package references for the demo. |

Tasks 1–3 are worth doing regardless of whether Zoekt lands — they are the
difference between a scanner and a service. Task 2 is where multi-repo either
works or is quietly wrong: get `indexable_targets` deduplicating before any
indexing code exists to duplicate work. Task 9 can ship as soon as the worker
writes progress, even if Zoekt is still the literal fallback.

---

## 9. Tests

| File | Asserts |
|---|---|
| `services/repo_indexer/tests/test_zoekt_shard.py` | Full index, delta index, corrupt shard raises rather than returning empty. |
| `.../tests/test_zoekt_query.py` | Regex family matching; the `-preview` identifier is a distinct finding. |
| `.../tests/test_astgrep_rules.py` | Each YAML rule against a fixture: call site matches, prose mentioning "imagen" does not. |
| `.../tests/test_fallback.py` | Zoekt down → literal results, no exception, warning logged. |
| `.../tests/test_store.py` | Upsert idempotency; replaying a push changes no row count; deleted path retires rather than deletes. |
| `.../tests/test_multi_repo.py` | Two repos in one project index independently and both appear under the project. Same repo in two projects builds **one** shard and **one** set of rows. `indexable_targets` deduplicates `(repo, branch)`. |
| `.../tests/test_project_scope.py` | `workspace_path` isolation: a finding under `packages/web` is invisible to a project scoped to `packages/api`. A NULL `workspace_path` sees the whole repository. This is the tenancy test — treat a failure as a security bug. |
| `.../tests/test_shard_refcount.py` | Removing a repo from one of two projects keeps the shard; removing it from both drops it. Revoked access retires the shard. |
| `.../tests/test_index_progress.py` | `set_index_progress` then `indexing_for_project`: one of two repos indexing → project status `indexing` and averaged `%`; all `ready` → banner would hide. |
| `packages/state/tests/test_indexing_route.py` | `GET /api/projects/{id}/indexing` shape matches what `CodebaseTab` polls. |
| `tests/integration/test_push_to_inventory.py` | Push webhook to `provider_usages` rows against a fixture repo. Push to an unimported branch is dropped before any fetch. |
| `tests/integration/test_manifest_fanout.py` | One manifest, one project with a frontend and a backend repo both affected → two `ImpactAnalysisRequested` events, two runs, two PRs. |
| `tests/integration/test_storygen_inventory.py` | Inventory at the pinned SHA equals `demo/storygen/expected-findings.yaml`. |

```bash
uv run pytest services/repo_indexer packages/repo_scan
uv run pytest tests/integration -k index
```

The Storygen test is the one that gates the demo. It must also cover the corrected
fixture — three GA identifiers mapping to two replacements, plus the retired
`-preview` identifier as its own finding.

---

## 10. Operational notes

**Shard storage.** ~3× source size, per `(repository, branch)` — not per
project, so a repository imported by ten projects costs one shard. Budget by
distinct indexed branches, which is what `indexable_targets` returns. Persistent
disk on GKE, or a Cloud Run volume mount. Cold start without a mounted volume
means a full rebuild — the reason this worker may need GKE rather than Cloud Run.

**Zoekt is batch, not a file watcher.** Nothing detects changes on its own; a
push event triggers a re-index. That is exactly the shape a webhook provides,
and it is why the 0.13 s delta number is the one that matters rather than the
cold-build number.

**Shards drift.** A missed webhook leaves a shard behind `HEAD`. Reconcile
nightly by comparing `repo_index_state.indexed_sha` against the branch head and
re-indexing the difference. The same job reconciles tenancy: every row in
`indexable_targets()` should have a shard, every shard should have a positive
reference count, and anything else is either an unindexed repository or an
orphan holding disk.

**Memory.** Zoekt memory-maps shards; the working set is the query set, not the
corpus. Fine on a 2 GB Cloud Run instance for hundreds of repositories.

**Failure is loud.** Every degradation — fallback used, shard rebuilt, scip
index incomplete — is an audit event and appears in the run trace. A quiet
degradation in this component looks exactly like good news, which is the one
thing it must never do.

---

## 11. References

- Zoekt — https://github.com/sourcegraph/zoekt (Apache-2.0)
- Zoekt design doc — https://github.com/sourcegraph/zoekt/blob/main/doc/design.md
- ast-grep — https://ast-grep.github.io (MIT)
- ast-grep rule reference — https://ast-grep.github.io/reference/rule.html
- scip-typescript — https://github.com/sourcegraph/scip-typescript
- SCIP protocol — https://github.com/sourcegraph/scip
- Gemini API File Search — https://ai.google.dev/gemini-api/docs/file-search
- Agent Retrieval — https://docs.cloud.google.com/gemini-enterprise-agent-platform/retrieval
