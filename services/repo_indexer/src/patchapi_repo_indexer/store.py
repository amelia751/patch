"""Persistence for the usage inventory and the shard state that produced it.

The tables are `provider_usages`, `repo_index_state`, and the
`project_provider_usages` view from `db/migrations/0007_provider_usages.sql`.
Two rules shape everything below (`repo-indexer.md` §3.1, §5.4):

Findings are facts about a `(repository, branch, commit)`, so they carry no
`project_id`. A repository imported by ten projects is one set of rows, and
project attribution is a join performed here and nowhere else.

A project's view of a shared repository can be narrower than the repository —
`workspaces.workspace_path` scopes it to a subfolder. That prefix filter lives
in the view, and `usages_for_project` is the only project-scoped read path, so
a call site cannot forget the filter and show one team another team's files.

Connections arrive from the caller so a worker can wrap a full index pass in one
transaction. Database failures propagate: a caller that cannot reach Postgres
knows nothing about a repository, and must not report that as "no usages".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from packages.events.console_notify import EVENT_INDEXING, notify_console
from patchapi_repo_indexer.config import INDEXER_VERSION, SCANNER_VERSION
from patchapi_repo_indexer.models import ApiUsageInventory, ApiUsageRecord

log = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - import cost is paid only by type checkers
    from collections.abc import Sequence

    import asyncpg

# Mirrors the `index_status` enum in 0007. Kept as a closed set here so an
# unknown status is rejected before it reaches the database, where the CHECK
# would surface as an opaque driver error.
IndexStatus = Literal["idle", "indexing", "ready", "error"]
INDEX_STATUSES: Final[frozenset[str]] = frozenset({"idle", "indexing", "ready", "error"})

MIN_PROGRESS: Final[int] = 0
MAX_PROGRESS: Final[int] = 100

# The unique key of `provider_usages`. Two scanner hits that collapse to the
# same key are one row, and Postgres refuses to update the same row twice in
# one statement, so an inventory is deduplicated on this key before it is
# written.
_USAGE_KEY: Final[tuple[str, ...]] = (
    "file_path",
    "line_start",
    "identifier",
    "detection_layer",
)

# Every `(repository, branch)` a project imported: the repository's default
# branch, plus every branch a workspace pinned. Both are indexed, because the
# `project_provider_usages` view resolves a finding against
# `COALESCE(workspaces.repo_branch, project_repositories.default_branch)` and
# so admits findings on either. Workspaces with no `repository_id` are absent
# for the same reason they are absent from the view: nothing joins them to a
# repository row.
_TARGETS_SQL: Final[str] = """
SELECT pr.full_name AS repository, pr.default_branch AS branch
FROM project_repositories pr
WHERE $1::uuid IS NULL OR pr.project_id = $1::uuid
UNION
SELECT pr.full_name AS repository, w.repo_branch AS branch
FROM workspaces w
JOIN project_repositories pr ON pr.id = w.repository_id
WHERE $1::uuid IS NULL OR pr.project_id = $1::uuid
"""


@dataclass(frozen=True, slots=True)
class PersistResult:
    """How many inventory rows were new and how many were re-observations."""

    inserted: int
    updated: int

    @property
    def total(self) -> int:
        return self.inserted + self.updated


@dataclass(frozen=True, slots=True)
class IndexTarget:
    """One `(repository, branch)` pair worth indexing, however many projects want it."""

    repository: str
    branch: str


@dataclass(frozen=True, slots=True)
class ProjectScope:
    """One project's window onto a repository.

    `path_prefix` is `workspaces.workspace_path`; `None` means the project
    imported the whole repository. A repository can yield several scopes for one
    project when the project pinned more than one workspace at that branch.
    """

    project_id: UUID
    project_repository_id: UUID
    kind: str
    path_prefix: str | None


@dataclass(frozen=True, slots=True)
class ProjectUsage:
    """A finding, with the repository it belongs to inside the project.

    `repo-indexer.md` §5.4 types this read as a bare `ApiUsageRecord`. A record
    carries no repository, and a project holds many, so the record is returned
    alongside the attribution a multi-repository project needs to route it to
    the right run and the right pull request.
    """

    project_id: UUID
    project_repository_id: UUID
    repository: str
    branch: str
    kind: str
    observed_sha: str
    record: ApiUsageRecord


@dataclass(frozen=True, slots=True)
class RepoIndexState:
    """The `repo_index_state` row for one `(repository, branch)`."""

    repository: str
    branch: str
    status: IndexStatus
    progress_percent: int
    indexed_sha: str | None
    shard_path: str | None
    indexer_version: str
    scanner_version: str
    last_full_index: datetime | None
    last_delta_index: datetime | None
    file_count: int
    reference_count: int
    error_message: str | None


@dataclass(frozen=True, slots=True)
class RepositoryIndexing:
    """One row of the Codebase tab banner's per-repository breakdown."""

    repository: str
    branch: str
    status: IndexStatus
    progress_percent: int


@dataclass(frozen=True, slots=True)
class ProjectIndexingStatus:
    """The `GET /api/projects/{id}/indexing` payload (`schema.md` §13)."""

    status: IndexStatus
    progress_percent: int
    repositories: tuple[RepositoryIndexing, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialize to the wire shape the Codebase tab polls.

        The wire calls a repository `full_name`, matching the console's
        `project_repositories` row; this module calls it `repository`, matching
        the indexer's tables.
        """
        return {
            "status": self.status,
            "progress_percent": self.progress_percent,
            "repositories": [
                {
                    "full_name": repo.repository,
                    "branch": repo.branch,
                    "status": repo.status,
                    "progress_percent": repo.progress_percent,
                }
                for repo in self.repositories
            ],
        }


def _deduplicate(usages: Sequence[ApiUsageRecord]) -> list[ApiUsageRecord]:
    """Collapse records that share the `provider_usages` unique key, last wins."""
    unique: dict[tuple[Any, ...], ApiUsageRecord] = {}
    for usage in usages:
        unique[tuple(getattr(usage, field) for field in _USAGE_KEY)] = usage
    return list(unique.values())


async def persist_inventory(
    conn: asyncpg.Connection, inventory: ApiUsageInventory
) -> PersistResult:
    """Write an inventory's findings, upserting on the unique key.

    Idempotent by construction: replaying the same push updates the rows it
    already wrote instead of duplicating them, which is what lets Pub/Sub
    deliver at-least-once without corrupting the inventory. Rows are never
    deleted here — a finding that has gone away is retired by `retire_paths`.

    A row that reappears at a later commit has `retired_at` cleared: the
    identifier is in the file again, and leaving it retired would hide a real
    usage from every project.
    """
    records = _deduplicate(inventory.usages)
    if not records:
        return PersistResult(inserted=0, updated=0)

    rows = await conn.fetch(
        """
        INSERT INTO provider_usages (
            repository, branch, provider, identifier, surface, file_path,
            line_start, line_end, usage_kind, detection_layer, confidence,
            excerpt, observed_sha
        )
        SELECT $1, $2, $3,
               t.identifier, t.surface, t.file_path, t.line_start, t.line_end,
               t.usage_kind::usage_kind, t.detection_layer::detection_layer,
               t.confidence, t.excerpt, $4
        FROM unnest(
            $5::text[], $6::text[], $7::text[], $8::int[], $9::int[],
            $10::text[], $11::text[], $12::real[], $13::text[]
        ) AS t(
            identifier, surface, file_path, line_start, line_end,
            usage_kind, detection_layer, confidence, excerpt
        )
        ON CONFLICT (repository, branch, file_path, line_start, identifier, detection_layer)
        DO UPDATE SET
            provider     = EXCLUDED.provider,
            surface      = EXCLUDED.surface,
            line_end     = EXCLUDED.line_end,
            usage_kind   = EXCLUDED.usage_kind,
            confidence   = EXCLUDED.confidence,
            excerpt      = EXCLUDED.excerpt,
            observed_sha = EXCLUDED.observed_sha,
            retired_at   = NULL,
            -- `now()` is transaction time, so a whole index pass would stamp
            -- one instant. `last seen` is an observation, not a transaction.
            last_seen_at = clock_timestamp()
        RETURNING (xmax = 0) AS inserted
        """,
        inventory.repository,
        inventory.branch,
        inventory.provider,
        inventory.observed_sha,
        [record.identifier for record in records],
        [record.surface for record in records],
        [record.file_path for record in records],
        [record.line_start for record in records],
        [record.line_end for record in records],
        [str(record.usage_kind) for record in records],
        [record.detection_layer for record in records],
        [float(record.confidence) for record in records],
        [record.excerpt for record in records],
    )
    inserted = sum(1 for row in rows if row["inserted"])
    return PersistResult(inserted=inserted, updated=len(rows) - inserted)


async def retire_paths(
    conn: asyncpg.Connection,
    repository: str,
    branch: str,
    paths: Sequence[str],
    sha: str,
) -> int:
    """Retire live findings in `paths` that were not re-observed at `sha`.

    A file that was deleted, or whose identifier was migrated away, keeps its
    history: the row is marked `retired_at` rather than deleted, so the record
    of what a repository used at an earlier commit survives the fix.

    The `sha` guard is what makes the delta path safe to call in the natural
    order. A push handler persists the inventory for the changed files first —
    stamping every surviving finding with the head SHA — then retires those same
    paths. Without the guard the second call would retire what the first just
    wrote.
    """
    if not paths:
        return 0
    return len(
        await conn.fetch(
            """
            UPDATE provider_usages
            SET retired_at = clock_timestamp()
            WHERE repository = $1
              AND branch = $2
              AND file_path = ANY($3::text[])
              AND retired_at IS NULL
              AND observed_sha IS DISTINCT FROM $4
            RETURNING id
            """,
            repository,
            branch,
            list(paths),
            sha,
        )
    )


def _state(row: Any) -> RepoIndexState:
    return RepoIndexState(
        repository=row["repository"],
        branch=row["branch"],
        status=row["status"],
        progress_percent=row["progress_percent"],
        indexed_sha=row["indexed_sha"],
        shard_path=row["shard_path"],
        indexer_version=row["indexer_version"],
        scanner_version=row["scanner_version"],
        last_full_index=row["last_full_index"],
        last_delta_index=row["last_delta_index"],
        file_count=row["file_count"],
        reference_count=row["reference_count"],
        error_message=row["error_message"],
    )


async def load_state(
    conn: asyncpg.Connection, repository: str, branch: str
) -> RepoIndexState | None:
    """Return the shard state for one target, or `None` if it was never indexed."""
    row = await conn.fetchrow(
        "SELECT * FROM repo_index_state WHERE repository = $1 AND branch = $2",
        repository,
        branch,
    )
    return None if row is None else _state(row)


async def record_state(conn: asyncpg.Connection, state: RepoIndexState) -> None:
    """Upsert the shard state for one target.

    `reference_count` is written only when the row is created. It belongs to
    `acquire_shard` / `release_shard`, and a worker that read the state before
    another project imported the same repository must not write a stale count
    back over the acquisition.
    """
    _check_status(state.status)
    _check_progress(state.progress_percent)
    await conn.execute(
        """
        INSERT INTO repo_index_state (
            repository, branch, status, progress_percent, indexed_sha, shard_path,
            indexer_version, scanner_version, last_full_index, last_delta_index,
            file_count, reference_count, error_message
        )
        VALUES ($1, $2, $3::index_status, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        ON CONFLICT (repository, branch) DO UPDATE SET
            status           = EXCLUDED.status,
            progress_percent = EXCLUDED.progress_percent,
            indexed_sha      = EXCLUDED.indexed_sha,
            shard_path       = EXCLUDED.shard_path,
            indexer_version  = EXCLUDED.indexer_version,
            scanner_version  = EXCLUDED.scanner_version,
            last_full_index  = EXCLUDED.last_full_index,
            last_delta_index = EXCLUDED.last_delta_index,
            file_count       = EXCLUDED.file_count,
            error_message    = EXCLUDED.error_message
        """,
        state.repository,
        state.branch,
        state.status,
        state.progress_percent,
        state.indexed_sha,
        state.shard_path,
        state.indexer_version,
        state.scanner_version,
        state.last_full_index,
        state.last_delta_index,
        state.file_count,
        state.reference_count,
        state.error_message,
    )
    await wake_console(conn, state.repository, state.branch)


async def indexable_targets(conn: asyncpg.Connection) -> list[IndexTarget]:
    """Every distinct `(repository, branch)` any project imported.

    Deduplicated, because the indexing unit is the repository and not the
    project: two projects importing the same repository is one shard and one set
    of findings, never two.
    """
    rows = await conn.fetch(
        f"SELECT repository, branch FROM ({_TARGETS_SQL}) t ORDER BY repository, branch",
        None,
    )
    return [IndexTarget(repository=row["repository"], branch=row["branch"]) for row in rows]


async def projects_for(
    conn: asyncpg.Connection, repository: str, branch: str
) -> list[ProjectScope]:
    """Every project scope a finding at `(repository, branch)` could belong to.

    The join and the branch resolution match `project_provider_usages` exactly,
    so the set of projects a push fans out to is the same set that can read the
    rows it wrote.
    """
    rows = await conn.fetch(
        """
        SELECT p.id AS project_id,
               pr.id AS project_repository_id,
               pr.kind::text AS kind,
               w.workspace_path AS path_prefix
        FROM project_repositories pr
        JOIN projects p ON p.id = pr.project_id
        LEFT JOIN workspaces w ON w.repository_id = pr.id AND w.repo_branch = $2
        WHERE pr.full_name = $1
          AND $2 = COALESCE(w.repo_branch, pr.default_branch)
        ORDER BY p.id, pr.id, w.workspace_path NULLS FIRST
        """,
        repository,
        branch,
    )
    return [
        ProjectScope(
            project_id=row["project_id"],
            project_repository_id=row["project_repository_id"],
            kind=row["kind"],
            path_prefix=row["path_prefix"],
        )
        for row in rows
    ]


async def usages_for_project(
    conn: asyncpg.Connection, project_id: UUID, identifiers: Sequence[str]
) -> list[ProjectUsage]:
    """Live findings for `identifiers` visible to one project.

    Reads `project_provider_usages` and never `provider_usages`, so the
    `workspace_path` prefix filter is applied by the view rather than by
    whichever caller remembered it. An empty `identifiers` list returns nothing:
    a manifest that watches no identifier affects no code, and widening that to
    "every finding" would leak the whole inventory into an unrelated run.
    """
    if not identifiers:
        return []
    rows = await conn.fetch(
        """
        SELECT project_id, project_repository_id, kind::text AS kind, repository, branch,
               provider, identifier, surface, file_path, line_start, line_end,
               usage_kind::text AS usage_kind, detection_layer::text AS detection_layer,
               confidence, excerpt, observed_sha
        FROM project_provider_usages
        WHERE project_id = $1 AND identifier = ANY($2::text[])
        ORDER BY repository, file_path, line_start, identifier
        """,
        project_id,
        list(identifiers),
    )
    return [
        ProjectUsage(
            project_id=row["project_id"],
            project_repository_id=row["project_repository_id"],
            repository=row["repository"],
            branch=row["branch"],
            kind=row["kind"],
            observed_sha=row["observed_sha"],
            record=ApiUsageRecord.model_validate(
                {
                    "provider": row["provider"],
                    "identifier": row["identifier"],
                    "surface": row["surface"],
                    "file_path": row["file_path"],
                    "line_start": row["line_start"],
                    "line_end": row["line_end"],
                    "usage_kind": row["usage_kind"],
                    "detection_layer": row["detection_layer"],
                    "confidence": row["confidence"],
                    "excerpt": row["excerpt"],
                }
            ),
        )
        for row in rows
    ]


def _check_status(status: str) -> None:
    if status not in INDEX_STATUSES:
        known = ", ".join(sorted(INDEX_STATUSES))
        raise ValueError(f"unknown index status {status!r}; known statuses: {known}")


def _check_progress(progress_percent: int) -> None:
    if not MIN_PROGRESS <= progress_percent <= MAX_PROGRESS:
        raise ValueError(
            f"progress_percent must be between {MIN_PROGRESS} and {MAX_PROGRESS},"
            f" got {progress_percent}"
        )


async def set_index_progress(
    conn: asyncpg.Connection,
    repository: str,
    branch: str,
    *,
    status: IndexStatus,
    progress_percent: int,
    error_message: str | None = None,
) -> None:
    """Publish indexing progress for one target. Drives the Codebase tab banner.

    Only the banner's three columns move. Shard identity — `indexed_sha`,
    `shard_path`, `reference_count` — is written by the pass that actually
    produced it, so a progress ping cannot claim an index that did not finish.
    """
    _check_status(status)
    _check_progress(progress_percent)
    await conn.execute(
        """
        INSERT INTO repo_index_state (
            repository, branch, status, progress_percent, error_message,
            indexer_version, scanner_version
        )
        VALUES ($1, $2, $3::index_status, $4, $5, $6, $7)
        ON CONFLICT (repository, branch) DO UPDATE SET
            status           = EXCLUDED.status,
            progress_percent = EXCLUDED.progress_percent,
            error_message    = EXCLUDED.error_message
        """,
        repository,
        branch,
        status,
        progress_percent,
        error_message,
        INDEXER_VERSION,
        SCANNER_VERSION,
    )
    await wake_console(conn, repository, branch)


async def wake_console(conn: asyncpg.Connection, repository: str, branch: str) -> None:
    """Wake every project console that imports this target.

    Progress pings are autocommit, so the banner can move during the pass.
    `record_state` runs inside the index transaction, so the ready wake waits
    for that commit. A failure here is logged, never raised: the rows are
    already the truth, and the dashboard falls back to polling.
    """
    try:
        scopes = await projects_for(conn, repository, branch)
    except Exception:
        log.warning(
            "console wake could not resolve projects for %s@%s",
            repository,
            branch,
            exc_info=True,
        )
        return
    seen: set[UUID] = set()
    for scope in scopes:
        if scope.project_id in seen:
            continue
        seen.add(scope.project_id)
        try:
            await notify_console(conn, event_type=EVENT_INDEXING, project_id=scope.project_id)
        except Exception:
            log.warning(
                "console NOTIFY failed for project %s",
                scope.project_id,
                exc_info=True,
            )


def _rollup(repositories: Sequence[RepositoryIndexing]) -> tuple[IndexStatus, int]:
    """Reduce per-repository state to the one banner a project shows.

    `repo-indexer.md` §7.6: any target indexing wins; an error shows only once
    nothing is still running; the bar is the average over the targets that are
    actually indexing, so two repositories at 20% and 80% read 50%.
    """
    if not repositories:
        return "idle", 0
    indexing = [repo.progress_percent for repo in repositories if repo.status == "indexing"]
    if indexing:
        # Half-up, so a project is never shown less progress than its average.
        return "indexing", int(sum(indexing) / len(indexing) + 0.5)
    if any(repo.status == "error" for repo in repositories):
        return "error", 0
    if all(repo.status == "ready" for repo in repositories):
        return "ready", MAX_PROGRESS
    return "idle", 0


async def indexing_for_project(conn: asyncpg.Connection, project_id: UUID) -> ProjectIndexingStatus:
    """The indexing banner for one project, rolled up over its imported targets.

    A target with no `repo_index_state` row reads as `idle`: it was imported but
    nothing has indexed it yet, which is not an error and is not readiness.
    """
    rows = await conn.fetch(
        f"""
        SELECT t.repository,
               t.branch,
               COALESCE(s.status::text, 'idle') AS status,
               COALESCE(s.progress_percent, 0) AS progress_percent
        FROM ({_TARGETS_SQL}) t
        LEFT JOIN repo_index_state s
               ON s.repository = t.repository AND s.branch = t.branch
        ORDER BY t.repository, t.branch
        """,
        project_id,
    )
    repositories = tuple(
        RepositoryIndexing(
            repository=row["repository"],
            branch=row["branch"],
            status=row["status"],
            progress_percent=row["progress_percent"],
        )
        for row in rows
    )
    status, progress_percent = _rollup(repositories)
    return ProjectIndexingStatus(
        status=status, progress_percent=progress_percent, repositories=repositories
    )


async def acquire_shard(
    conn: asyncpg.Connection,
    repository: str,
    branch: str,
    *,
    shard_path: str | None = None,
) -> int:
    """Take a reference on a target's shard and return the new count.

    Called once per `project_repositories` row rather than once per project, so
    importing an already-indexed repository into a second project costs a
    counter bump and no clone.
    """
    count = await conn.fetchval(
        """
        INSERT INTO repo_index_state (
            repository, branch, reference_count, shard_path,
            indexer_version, scanner_version
        )
        VALUES ($1, $2, 1, $3, $4, $5)
        ON CONFLICT (repository, branch) DO UPDATE SET
            reference_count = repo_index_state.reference_count + 1,
            shard_path = COALESCE(EXCLUDED.shard_path, repo_index_state.shard_path)
        RETURNING reference_count
        """,
        repository,
        branch,
        shard_path,
        INDEXER_VERSION,
        SCANNER_VERSION,
    )
    return int(count)


async def release_shard(conn: asyncpg.Connection, repository: str, branch: str) -> int:
    """Drop one reference and return the new count.

    The shard is dropped only at zero — one project removing a repository must
    not blind the other projects that still import it. Dropping clears the shard
    pointer and returns the target to `idle`; the row itself stays, because the
    findings it produced are still history and re-importing should not read as a
    repository nobody ever indexed.
    """
    count = await conn.fetchval(
        """
        UPDATE repo_index_state
        SET reference_count = GREATEST(reference_count - 1, 0),
            shard_path = CASE WHEN reference_count - 1 <= 0 THEN NULL ELSE shard_path END,
            status = CASE WHEN reference_count - 1 <= 0
                          THEN 'idle'::index_status ELSE status END,
            progress_percent = CASE WHEN reference_count - 1 <= 0
                                    THEN 0 ELSE progress_percent END
        WHERE repository = $1 AND branch = $2
        RETURNING reference_count
        """,
        repository,
        branch,
    )
    # No row means nothing ever took a reference. Releasing an unheld shard is a
    # no-op, not an error: repository removal is replayed like every other event.
    if count is None:
        return 0
    await wake_console(conn, repository, branch)
    return int(count)


__all__ = [
    "INDEX_STATUSES",
    "IndexStatus",
    "IndexTarget",
    "PersistResult",
    "ProjectIndexingStatus",
    "ProjectScope",
    "ProjectUsage",
    "RepoIndexState",
    "RepositoryIndexing",
    "acquire_shard",
    "indexable_targets",
    "indexing_for_project",
    "load_state",
    "persist_inventory",
    "projects_for",
    "record_state",
    "release_shard",
    "retire_paths",
    "set_index_progress",
    "usages_for_project",
    "wake_console",
]
